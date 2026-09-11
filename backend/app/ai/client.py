"""Backend AI client abstraction for the HELIOS AI Intelligence Layer.

Supports primary Gemini models with automatic fallback to OpenRouter
(e.g., nvidia/nemotron-3.5-lightning:free with reasoning enabled) when Gemini is
unavailable or taking too long.
"""
from __future__ import annotations
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


def _strip_think_tags(text: str | None) -> str:
    """Strips internal thought blocks such as <think>...</think> from model outputs."""
    if not text:
        return ""
    # Strip closed think tags
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # If unclosed think tag exists
    if "<think>" in cleaned:
        parts = cleaned.split("</think>", 1)
        if len(parts) > 1:
            cleaned = parts[1]
        else:
            # Everything after <think> is thinking tokens
            idx = cleaned.find("<think>")
            cleaned = cleaned[:idx]
    return cleaned.strip()


class AiUnavailableError(RuntimeError):
    """Raised when the configured AI backend cannot be used."""


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeminiRawOutput:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: str | None = None
    reasoning_details: Any = None
    reasoning_tokens: int | None = None
    provider: str | None = None
    model: str | None = None


class OpenRouterClient:
    """OpenRouter client supporting OpenAI-compatible chat completions.

    Supports models such as nvidia/nemotron-3-super-120b-a12b:free, nvidia/nemotron-3.5-lightning:free,
    and multimodal investigation models like minimax/minimax-m3 and google/gemma-4-31b-it.
    """

    def __init__(
        self,
        api_key: str = "",
        gemma_api_key: str = "",
        model: str = "nvidia/nemotron-3-super-120b-a12b:free",
        fallback_model: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        reasoning_enabled: bool = True,
        reasoning_effort: str | None = None,
        reasoning_max_tokens: int | None = None,
    ):
        self.api_key = (api_key or "").strip()
        self.gemma_api_key = (gemma_api_key or "").strip()
        self.model = model or "nvidia/nemotron-3-super-120b-a12b:free"
        if fallback_model is not None:
            self.fallback_model = fallback_model
        elif "super" in self.model.lower():
            self.fallback_model = "nvidia/nemotron-3.5-lightning:free"
        elif ":free" in self.model:
            self.fallback_model = self.model.replace(":free", "")
        else:
            self.fallback_model = "nvidia/nemotron-3.5-lightning:free"
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.reasoning_enabled = bool(reasoning_enabled)
        self.reasoning_effort = reasoning_effort
        self.reasoning_max_tokens = reasoning_max_tokens
        self.provider = "openrouter"
        self.last_reasoning_details: Any = None
        self.error: str | None = None
        if not self.api_key and not self.gemma_api_key:
            self.error = "OPENROUTER_API_KEY_MISSING"

    @property
    def available(self) -> bool:
        return bool(self.api_key or self.gemma_api_key)

    def _get_api_key_for_model(self, model: str) -> str:
        lower = (model or "").lower()
        if ("gemma" in lower or "minimax" in lower) and self.gemma_api_key:
            return self.gemma_api_key
        return self.api_key or self.gemma_api_key

    def get_investigation_client(
        self,
        model: str = "minimax/minimax-m3",
        fallback_model: str = "google/gemma-4-31b-it",
    ) -> OpenRouterClient:
        key_for_model = self._get_api_key_for_model(model)
        if self.model == model and self.api_key == key_for_model and self.fallback_model == fallback_model:
            return self
        return OpenRouterClient(
            api_key=key_for_model,
            gemma_api_key=self.gemma_api_key,
            model=model,
            fallback_model=fallback_model,
            base_url=self.base_url,
            timeout_seconds=self.timeout_seconds,
            reasoning_enabled=True,
            reasoning_effort=self.reasoning_effort,
            reasoning_max_tokens=self.reasoning_max_tokens,
        )

    def _to_json_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(schema, dict):
            return schema
        out: dict[str, Any] = {}
        type_map = {
            "OBJECT": "object",
            "STRING": "string",
            "INTEGER": "integer",
            "NUMBER": "number",
            "BOOLEAN": "boolean",
            "ARRAY": "array",
        }
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                out[k] = type_map.get(v.upper(), v.lower())
            elif k == "properties" and isinstance(v, dict):
                out[k] = {pk: self._to_json_schema(pv) for pk, pv in v.items()}
            elif k == "items" and isinstance(v, dict):
                out[k] = self._to_json_schema(v)
            else:
                out[k] = v
        return out

    def _build_openai_tools(self, declarations: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not declarations:
            return None
        tools: list[dict[str, Any]] = []
        for d in declarations:
            tools.append({
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d.get("description", ""),
                    "parameters": self._to_json_schema(d.get("parameters", {})),
                },
            })
        return tools

    def _convert_contents(self, contents: list[dict[str, Any]], system_instruction: str | None = None) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        for msg in contents:
            role = msg.get("role", "user")
            parts = msg.get("parts", [])
            raw_content = msg.get("content")

            if role == "user":
                text_segments: list[str] = []
                image_segments: list[dict[str, Any]] = []

                if isinstance(raw_content, str) and raw_content:
                    text_segments.append(raw_content)
                elif isinstance(raw_content, list):
                    for item in raw_content:
                        if isinstance(item, str):
                            text_segments.append(item)
                        elif isinstance(item, dict):
                            if item.get("type") == "text":
                                text_segments.append(item.get("text", ""))
                            elif item.get("type") == "image_url":
                                image_segments.append(item)

                for p in parts:
                    if isinstance(p, dict):
                        if "text" in p and p["text"]:
                            text_segments.append(p["text"])
                        if "inline_data" in p:
                            idat = p["inline_data"]
                            mime = idat.get("mime_type", "image/jpeg")
                            data = idat.get("data", "")
                            image_segments.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{data}"},
                            })
                        elif "image_url" in p:
                            url_val = p["image_url"]
                            if isinstance(url_val, str):
                                image_segments.append({"type": "image_url", "image_url": {"url": url_val}})
                            elif isinstance(url_val, dict):
                                image_segments.append({"type": "image_url", "image_url": url_val})
                        elif "image_bytes" in p:
                            import base64
                            b64 = base64.b64encode(p["image_bytes"]).decode("utf-8")
                            mime = p.get("mime_type", "image/jpeg")
                            image_segments.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            })

                combined_text = "".join(text_segments)
                if image_segments:
                    user_content: list[dict[str, Any]] = []
                    if combined_text:
                        user_content.append({"type": "text", "text": combined_text})
                    user_content.extend(image_segments)
                    messages.append({"role": "user", "content": user_content})
                else:
                    messages.append({"role": "user", "content": combined_text})

            elif role in ("model", "assistant"):
                text = ""
                if isinstance(raw_content, str):
                    text = raw_content
                text = text + "".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)
                tool_calls: list[dict[str, Any]] = []
                for i, p in enumerate(parts):
                    if isinstance(p, dict) and "function_call" in p:
                        fc = p["function_call"]
                        tool_calls.append({
                            "id": f"call_{i+1}",
                            "type": "function",
                            "function": {
                                "name": fc.get("name", ""),
                                "arguments": json.dumps(fc.get("args", {})),
                            },
                        })
                if not tool_calls and isinstance(msg.get("tool_calls"), list):
                    tool_calls = msg["tool_calls"]

                entry: dict[str, Any] = {"role": "assistant"}
                if text:
                    entry["content"] = text
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                reasoning = msg.get("reasoning_details")
                if reasoning is None and self.last_reasoning_details is not None:
                    reasoning = self.last_reasoning_details
                if reasoning is not None:
                    entry["reasoning_details"] = reasoning
                messages.append(entry)
            elif role in ("function", "tool"):
                for i, p in enumerate(parts):
                    if "function_response" in p:
                        fr = p["function_response"]
                        fn_name = fr.get("name", "tool")
                        resp_content = json.dumps(fr.get("response", {}))
                        tool_id = f"call_{fn_name}"
                        # Prepend assistant message with tool_calls if absent to maintain valid OpenAI schema
                        if not messages or messages[-1].get("role") != "assistant" or "tool_calls" not in messages[-1]:
                            synthetic_assistant: dict[str, Any] = {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": tool_id,
                                    "type": "function",
                                    "function": {"name": fn_name, "arguments": "{}"},
                                }],
                            }
                            if self.last_reasoning_details is not None:
                                synthetic_assistant["reasoning_details"] = self.last_reasoning_details
                            messages.append(synthetic_assistant)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": fn_name,
                            "content": resp_content,
                        })
        return messages

    @staticmethod
    def _extract_reasoning_tokens(data: dict[str, Any]) -> int | None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None
        details = usage.get("completion_tokens_details") or usage.get("completionTokensDetails")
        if isinstance(details, dict):
            tokens = details.get("reasoning_tokens") if "reasoning_tokens" in details else details.get("reasoningTokens")
            if tokens is not None:
                try:
                    return int(tokens)
                except (ValueError, TypeError):
                    pass
        tokens = usage.get("reasoning_tokens") if "reasoning_tokens" in usage else usage.get("reasoningTokens")
        if tokens is not None:
            try:
                return int(tokens)
            except (ValueError, TypeError):
                pass
        return None

    def generate(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        response_json: bool = True,
    ) -> GeminiRawOutput:
        if not self.available:
            return GeminiRawOutput(error=self.error or "OPENROUTER_UNAVAILABLE", provider="openrouter")
        if requests is None:
            return GeminiRawOutput(error="REQUESTS_LIBRARY_MISSING", provider="openrouter")

        messages = self._convert_contents(contents, system_instruction=system_instruction)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        reasoning_payload: dict[str, Any] = {"enabled": bool(self.reasoning_enabled)}
        # OpenRouter requires mutually exclusive reasoning.max_tokens OR reasoning.effort
        if self.reasoning_max_tokens:
            reasoning_payload["max_tokens"] = self.reasoning_max_tokens
        elif self.reasoning_effort:
            reasoning_payload["effort"] = self.reasoning_effort
        payload["reasoning"] = reasoning_payload

        if temperature is not None:
            payload["temperature"] = temperature
        if max_output_tokens:
            payload["max_tokens"] = min(int(max_output_tokens), 2048)
        else:
            payload["max_tokens"] = 1500

        openai_tools = self._build_openai_tools(tools)
        if openai_tools:
            payload["tools"] = openai_tools

        active_api_key = self._get_api_key_for_model(payload.get("model", self.model))
        headers = {
            "Authorization": f"Bearer {active_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        try:
            resp = requests.post(url=url, headers=headers, data=json.dumps(payload), timeout=self.timeout_seconds)
            # If the model rejects effort/reasoning format in API parameters, retry with minimal {"enabled": True}
            if resp.status_code == 400 and ("reasoning" in resp.text.lower() or "effort" in resp.text.lower()) and payload.get("reasoning") != {"enabled": True}:
                payload["reasoning"] = {"enabled": True}
                resp = requests.post(url=url, headers=headers, data=json.dumps(payload), timeout=self.timeout_seconds)
            # If the model does not support tool calling in API parameters, retry without tools
            if resp.status_code == 400 and ("tools" in resp.text.lower() or "functions" in resp.text.lower()) and "tools" in payload:
                del payload["tools"]
                resp = requests.post(url=url, headers=headers, data=json.dumps(payload), timeout=self.timeout_seconds)
            # If the model rejected because it's no longer free (HTTP 404) or rate-limited (HTTP 429),
            # retry with the standard non-free model before falling back to Gemma
            if resp.status_code in (404, 429) and ":free" in payload.get("model", ""):
                non_free_model = payload["model"].replace(":free", "")
                logger.warning("Model %s returned HTTP %s; retrying with %s", payload.get("model"), resp.status_code, non_free_model)
                payload["model"] = non_free_model
                active_key = self._get_api_key_for_model(non_free_model)
                headers["Authorization"] = f"Bearer {active_key}"
                resp = requests.post(url=url, headers=headers, data=json.dumps(payload), timeout=self.timeout_seconds)
            # If the endpoint still fails (4xx or 5xx), fallback to fallback_model (e.g. google/gemma-4-31b-it)
            if resp.status_code != 200 and self.fallback_model and payload.get("model") != self.fallback_model:
                logger.warning("Model %s returned HTTP %s; falling back to %s", payload.get("model"), resp.status_code, self.fallback_model)
                payload["model"] = self.fallback_model
                fallback_key = self._get_api_key_for_model(self.fallback_model)
                headers["Authorization"] = f"Bearer {fallback_key}"
                resp = requests.post(url=url, headers=headers, data=json.dumps(payload), timeout=self.timeout_seconds)

            if resp.status_code != 200:
                return GeminiRawOutput(
                    error=f"OPENROUTER_HTTP_{resp.status_code}: {resp.text[:200]}",
                    provider="openrouter",
                    model=payload.get("model", self.model),
                )

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return GeminiRawOutput(error="EMPTY_RESPONSE", provider="openrouter", model=payload.get("model", self.model))

            choice = choices[0]
            msg = choice.get("message") or {}
            raw_content = msg.get("content")
            text = _strip_think_tags(raw_content) if raw_content is not None else None
            reasoning_details = msg.get("reasoning_details")
            reasoning_tokens = self._extract_reasoning_tokens(data)
            if reasoning_details is not None:
                self.last_reasoning_details = reasoning_details

            raw_tool_calls = msg.get("tool_calls") or []
            tool_calls: list[ToolCall] = []
            for tc in raw_tool_calls:
                func = tc.get("function") or {}
                name = func.get("name") or ""
                raw_args = func.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except Exception:
                    args = {"arguments": raw_args}
                tool_calls.append(ToolCall(name=name, args=args))

            if text is None and not tool_calls:
                raw_reasoning = msg.get("reasoning")
                if not raw_reasoning and isinstance(reasoning_details, list) and reasoning_details:
                    raw_reasoning = reasoning_details[0].get("text")
                if raw_reasoning:
                    text = _strip_think_tags(raw_reasoning)
                else:
                    return GeminiRawOutput(error="EMPTY_RESPONSE", provider="openrouter", model=payload.get("model", self.model))

            return GeminiRawOutput(
                text=text,
                tool_calls=tool_calls,
                reasoning_details=reasoning_details,
                reasoning_tokens=reasoning_tokens,
                provider="openrouter",
                model=payload.get("model", self.model),
            )
        except Exception as exc:
            # If primary timed out or failed with request error, automatically try fallback_model
            if self.fallback_model and payload.get("model") != self.fallback_model:
                logger.warning("Model %s failed (%s); retrying with fallback %s", payload.get("model"), exc, self.fallback_model)
                payload["model"] = self.fallback_model
                fallback_key = self._get_api_key_for_model(self.fallback_model)
                headers["Authorization"] = f"Bearer {fallback_key}"
                try:
                    resp = requests.post(url=url, headers=headers, data=json.dumps(payload), timeout=self.timeout_seconds)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices") or []
                        if choices:
                            choice = choices[0]
                            msg = choice.get("message") or {}
                            fb_content = msg.get("content")
                            fb_text = _strip_think_tags(fb_content) if fb_content is not None else None
                            return GeminiRawOutput(
                                text=fb_text,
                                tool_calls=[],
                                reasoning_details=msg.get("reasoning_details"),
                                reasoning_tokens=self._extract_reasoning_tokens(data),
                                provider="openrouter",
                                model=self.fallback_model,
                            )
                except Exception:
                    pass
            return GeminiRawOutput(
                error=f"OPENROUTER_REQUEST_FAILED: {type(exc).__name__}: {exc}",
                provider="openrouter",
                model=payload.get("model", self.model),
            )

    def stream(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ):
        """Generator yielding streaming text tokens from OpenRouter (Cloud Super with fallback to Cloud Light)."""
        if not self.available or requests is None:
            return

        messages = self._convert_contents(contents, system_instruction=system_instruction)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature if temperature is not None else 0.2,
            "max_tokens": max_output_tokens if max_output_tokens else 2048,
        }
        url = f"{self.base_url}/chat/completions"

        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        for mod in models_to_try:
            payload["model"] = mod
            active_key = self._get_api_key_for_model(mod)
            headers = {
                "Authorization": f"Bearer {active_key}",
                "Content-Type": "application/json",
            }
            has_yielded = False
            try:
                resp = requests.post(url=url, headers=headers, data=json.dumps(payload), stream=True, timeout=self.timeout_seconds)
                if resp.status_code == 200:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                        if decoded.startswith("data: "):
                            data_str = decoded[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices") or []
                                if choices:
                                    delta = choices[0].get("delta") or {}
                                    token = delta.get("content")
                                    if token:
                                        has_yielded = True
                                        yield token
                            except Exception:
                                continue
                    if has_yielded:
                        return
            except Exception:
                continue


class OllamaClient:
    """Multi-tier client for HELIOS AI text chat and daily briefings.

    Defined Resolution Hierarchy:
    1. Cloud Super: nvidia/nemotron-3-super-120b-a12b:free (OpenRouter)
    2. Cloud Light: nvidia/nemotron-3.5-lightning:free (OpenRouter)
    3. Local Ollama: qwen3:4b (http://127.0.0.1:11434)
    4. Local HELIOS AI: deterministic telemetry synthesis (Last line of defense)

    When offline or without internet:
    Local Ollama (qwen3:4b) -> Local HELIOS AI
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:4b",
        timeout_seconds: float = 60.0,
        enabled: bool = True,
        openrouter_api_key: str = "",
        openrouter_gemma_api_key: str = "",
        openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free",
        openrouter_fallback_model: str = "nvidia/nemotron-3.5-lightning:free",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        openrouter_timeout_seconds: float = 30.0,
        openrouter_reasoning: bool = True,
        openrouter_reasoning_effort: str | None = "low",
        openrouter_reasoning_max_tokens: int | None = 400,
    ):
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.model = model or "qwen3:4b"
        self.timeout_seconds = float(timeout_seconds)
        self.enabled = bool(enabled)
        self.openrouter_api_key = (openrouter_api_key or "").strip()
        self.openrouter_gemma_api_key = (openrouter_gemma_api_key or "").strip()
        self.openrouter_model = openrouter_model or "nvidia/nemotron-3-super-120b-a12b:free"
        self.openrouter_fallback_model = openrouter_fallback_model or "nvidia/nemotron-3.5-lightning:free"
        self.openrouter_base_url = (openrouter_base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.openrouter_timeout_seconds = float(openrouter_timeout_seconds)
        self.openrouter_reasoning = bool(openrouter_reasoning)
        self.openrouter_reasoning_effort = openrouter_reasoning_effort
        self.openrouter_reasoning_max_tokens = openrouter_reasoning_max_tokens
        self.provider = "ollama"
        self.last_reasoning_details: Any = None
        self.error: str | None = None
        if not self.enabled:
            self.error = "HELIOS_AI_DISABLED"

        self._cloud_client: OpenRouterClient | None = None
        key = self.openrouter_api_key or self.openrouter_gemma_api_key
        if key:
            self._cloud_client = OpenRouterClient(
                api_key=key,
                gemma_api_key=self.openrouter_gemma_api_key or key,
                model=self.openrouter_model,
                fallback_model=self.openrouter_fallback_model,
                base_url=self.openrouter_base_url,
                timeout_seconds=self.openrouter_timeout_seconds,
                reasoning_enabled=self.openrouter_reasoning,
                reasoning_effort=self.openrouter_reasoning_effort,
                reasoning_max_tokens=self.openrouter_reasoning_max_tokens,
            )

    @property
    def available(self) -> bool:
        return self.enabled

    def get_investigation_client(
        self,
        model: str = "minimax/minimax-m3",
        fallback_model: str = "google/gemma-4-31b-it",
    ) -> OpenRouterClient:
        """Returns dedicated OpenRouter investigation client for Minimax M3 and Gemma 4 (UNTOUCHED)."""
        key = self.openrouter_gemma_api_key or self.openrouter_api_key
        return OpenRouterClient(
            api_key=key,
            gemma_api_key=self.openrouter_gemma_api_key or key,
            model=model,
            fallback_model=fallback_model,
            base_url=self.openrouter_base_url,
            timeout_seconds=self.openrouter_timeout_seconds,
            reasoning_enabled=self.openrouter_reasoning,
            reasoning_effort=self.openrouter_reasoning_effort,
            reasoning_max_tokens=self.openrouter_reasoning_max_tokens,
        )

    def _convert_contents(
        self, contents: list[dict[str, Any]], system_instruction: str | None = None
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        for msg in contents:
            role = msg.get("role", "user")
            if role in ("model", "assistant"):
                target_role = "assistant"
            elif role == "system":
                target_role = "system"
            else:
                target_role = "user"

            raw_content = msg.get("content")
            text = ""
            if isinstance(raw_content, str):
                text = raw_content
            elif isinstance(raw_content, list):
                for item in raw_content:
                    if isinstance(item, str):
                        text += item
                    elif isinstance(item, dict) and item.get("type") == "text":
                        text += item.get("text", "")

            parts = msg.get("parts", [])
            for p in parts:
                if isinstance(p, dict) and "text" in p and p["text"]:
                    text += p["text"]

            messages.append({"role": target_role, "content": text})

        return messages

    def generate(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        response_json: bool = False,
    ) -> GeminiRawOutput:
        """Executes request across defined hierarchy:
        Cloud Super -> Cloud Light -> Local Ollama -> Local HELIOS AI
        (Offline / No Internet: Local Ollama -> Local HELIOS AI)
        """
        if not self.enabled:
            return GeminiRawOutput(error=self.error or "HELIOS_AI_DISABLED", provider="ollama", model=self.model)

        # 1. Tier 1 & Tier 2: Try Cloud (Super -> Light via OpenRouter) when key is present
        if self._cloud_client and self._cloud_client.available:
            cloud_out = self._cloud_client.generate(
                contents=contents,
                system_instruction=system_instruction,
                tools=tools,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_json=response_json,
            )
            if not cloud_out.error and (cloud_out.text or cloud_out.tool_calls):
                return cloud_out

        # 2. Tier 3: Local Ollama (qwen3:4b)
        ollama_out = self._generate_ollama(
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_json=response_json,
        )
        if not ollama_out.error and ollama_out.text:
            return ollama_out

        # 3. Tier 4: Return error so caller falls back to Local HELIOS AI
        return GeminiRawOutput(
            error=ollama_out.error or "ALL_AI_PROVIDERS_UNAVAILABLE",
            reasoning_details=ollama_out.reasoning_details,
            provider="local",
            model="local-helios-ai",
        )

    def _generate_ollama(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        response_json: bool = False,
    ) -> GeminiRawOutput:
        if requests is None:
            return GeminiRawOutput(error="REQUESTS_LIBRARY_MISSING", provider="ollama", model=self.model)

        messages = self._convert_contents(contents, system_instruction=system_instruction)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else 0.2,
                "num_predict": max_output_tokens if max_output_tokens else 2048,
            },
        }
        if response_json:
            payload["format"] = "json"

        url = f"{self.base_url}/api/chat"
        try:
            resp = requests.post(url=url, json=payload, timeout=self.timeout_seconds)
            if resp.status_code != 200:
                return GeminiRawOutput(
                    error=f"OLLAMA_HTTP_{resp.status_code}: {resp.text[:200]}",
                    provider="ollama",
                    model=self.model,
                )

            data = resp.json()
            msg = data.get("message") or {}
            raw_text = msg.get("content") or ""
            thinking = msg.get("thinking")
            if thinking is not None:
                self.last_reasoning_details = thinking

            text = _strip_think_tags(raw_text)

            if not text:
                return GeminiRawOutput(
                    error="EMPTY_RESPONSE",
                    reasoning_details=thinking,
                    provider="ollama",
                    model=self.model,
                )

            return GeminiRawOutput(
                text=text,
                reasoning_details=thinking,
                provider="ollama",
                model=self.model,
            )
        except Exception as exc:
            return GeminiRawOutput(
                error=f"OLLAMA_REQUEST_FAILED: {type(exc).__name__}: {exc}",
                provider="ollama",
                model=self.model,
            )

    def stream(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ):
        """Streams tokens following the defined hierarchy:
        Cloud Super -> Cloud Light -> Local Ollama
        """
        if not self.enabled:
            return

        # 1. Tier 1 & Tier 2: Try Cloud streaming (Super -> Light)
        if self._cloud_client and self._cloud_client.available:
            has_yielded = False
            try:
                for token in self._cloud_client.stream(
                    contents=contents,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ):
                    has_yielded = True
                    yield token
            except Exception:
                pass
            if has_yielded:
                return

        # 2. Tier 3: Stream from Local Ollama (qwen3:4b)
        for token in self._stream_ollama(
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ):
            yield token

    def _stream_ollama(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
    ):
        if requests is None:
            return
        messages = self._convert_contents(contents, system_instruction=system_instruction)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature if temperature is not None else 0.2,
                "num_predict": max_output_tokens if max_output_tokens else 2048,
            },
        }
        url = f"{self.base_url}/api/chat"
        try:
            resp = requests.post(url=url, json=payload, stream=True, timeout=self.timeout_seconds)
            if resp.status_code != 200:
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
                    msg = chunk.get("message") or {}
                    token = msg.get("content", "")
                    if token:
                        yield token
                except Exception:
                    continue
        except Exception:
            return


class GeminiClient:
    """Gemini client with automatic fallback to OpenRouter when unavailable or timing out."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-3.5-flash-lite",
        enabled: bool = True,
        timeout_seconds: float = 30.0,
        gemini_timeout_seconds: float = 10.0,
        openrouter_api_key: str = "",
        openrouter_gemma_api_key: str = "",
        openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free",
        openrouter_fallback_model: str = "nvidia/nemotron-3.5-lightning:free",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        openrouter_timeout_seconds: float = 30.0,
        openrouter_reasoning: bool = True,
        openrouter_reasoning_effort: str | None = None,
        openrouter_reasoning_max_tokens: int | None = None,
    ):
        self.model = model or "gemini-3.5-flash-lite"
        self.enabled = bool(enabled)
        self.timeout_seconds = float(timeout_seconds)
        self.gemini_timeout_seconds = float(gemini_timeout_seconds) if gemini_timeout_seconds else 10.0
        self.openrouter_gemma_api_key = (openrouter_gemma_api_key or "").strip()
        self.provider: str | None = None
        self.error: str | None = None
        self._client: Any = None
        self._types: Any = None
        self.gemini_available: bool = False

        self._openrouter_client: OpenRouterClient | None = None
        if openrouter_api_key or openrouter_gemma_api_key:
            self._openrouter_client = OpenRouterClient(
                api_key=openrouter_api_key,
                gemma_api_key=openrouter_gemma_api_key,
                model=openrouter_model,
                fallback_model=openrouter_fallback_model,
                base_url=openrouter_base_url,
                timeout_seconds=openrouter_timeout_seconds,
                reasoning_enabled=openrouter_reasoning,
                reasoning_effort=openrouter_reasoning_effort,
                reasoning_max_tokens=openrouter_reasoning_max_tokens,
            )

        if not self.enabled:
            self.error = "HELIOS_AI_DISABLED"
            return

        if not api_key:
            if self._openrouter_client and self._openrouter_client.available:
                self.provider = "openrouter"
                self.model = self._openrouter_client.model
                self.error = None
            else:
                self.error = "GEMINI_API_KEY_MISSING"
            return

        try:
            from google import genai
            from google.genai import types as genai_types
            self._client = genai.Client(api_key=api_key)
            self._types = genai_types
            self.gemini_available = True
            self.provider = "gemini"
        except Exception as exc:
            self.gemini_available = False
            if self._openrouter_client and self._openrouter_client.available:
                self.provider = "openrouter"
                self.model = self._openrouter_client.model
                self.error = None
            else:
                self.error = f"GEMINI_UNAVAILABLE: {type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        return self.gemini_available or (self._openrouter_client is not None and self._openrouter_client.available)

    @property
    def fallback_available(self) -> bool:
        return self._openrouter_client is not None and self._openrouter_client.available

    def get_investigation_client(
        self,
        model: str = "minimax/minimax-m3",
        fallback_model: str = "google/gemma-4-31b-it",
    ) -> OpenRouterClient:
        """For image inputs and investigations, uses minimax/minimax-m3 with fallback to google/gemma-4-31b-it."""
        if self._openrouter_client is not None:
            return self._openrouter_client.get_investigation_client(model=model, fallback_model=fallback_model)
        key = self.openrouter_gemma_api_key or self.openrouter_api_key
        return OpenRouterClient(
            api_key=key,
            gemma_api_key=self.openrouter_gemma_api_key or key,
            model=model,
            fallback_model=fallback_model,
            reasoning_enabled=True,
        )

    def generate(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        response_json: bool = True,
    ) -> GeminiRawOutput:
        if not self.enabled:
            return GeminiRawOutput(error=self.error or "HELIOS_AI_DISABLED")

        if not self.gemini_available:
            if self.fallback_available and self._openrouter_client is not None:
                return self._openrouter_client.generate(
                    contents=contents,
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_json=response_json,
                )
            return GeminiRawOutput(error=self.error or "HELIOS_AI_UNAVAILABLE")

        timeout = self.gemini_timeout_seconds or self.timeout_seconds
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._generate_gemini,
                    contents,
                    system_instruction,
                    tools,
                    temperature,
                    max_output_tokens,
                    response_json,
                )
                output = future.result(timeout=timeout)
                if output.error and self.fallback_available and self._openrouter_client is not None:
                    logger.warning(
                        "Gemini returned error (%s); falling back to OpenRouter (%s)",
                        output.error,
                        self._openrouter_client.model,
                    )
                    return self._openrouter_client.generate(
                        contents=contents,
                        system_instruction=system_instruction,
                        tools=tools,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        response_json=response_json,
                    )
                return output
        except FutureTimeoutError:
            logger.warning(
                "Gemini request timed out after %.1fs; falling back to OpenRouter (%s)",
                timeout,
                getattr(self._openrouter_client, "model", "openrouter"),
            )
            if self.fallback_available and self._openrouter_client is not None:
                return self._openrouter_client.generate(
                    contents=contents,
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_json=response_json,
                )
            return GeminiRawOutput(
                error=f"GEMINI_TIMEOUT: Request exceeded {timeout}s (OpenRouter fallback unavailable: OPENROUTER_API_KEY is not configured in .env)",
                provider="gemini",
            )
        except Exception as exc:
            logger.warning(
                "Gemini request failed with exception (%s: %s); falling back to OpenRouter",
                type(exc).__name__,
                exc,
            )
            if self.fallback_available and self._openrouter_client is not None:
                return self._openrouter_client.generate(
                    contents=contents,
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_json=response_json,
                )
            return GeminiRawOutput(error=self._describe_error(exc), provider="gemini")

    def _generate_gemini(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None,
        tools: list[dict[str, Any]] | None,
        temperature: float,
        max_output_tokens: int,
        response_json: bool,
    ) -> GeminiRawOutput:
        try:
            converted = [self._content(message) for message in contents]
            tool_defs = self._build_tools(tools)
            attempts = 0
            while True:
                try:
                    response = self._generate_once(
                        converted, system_instruction, tool_defs, temperature, max_output_tokens, response_json
                    )
                    out = self._extract(response)
                    out.provider = "gemini"
                    return out
                except Exception as exc:
                    if attempts < 1 and self._retryable(exc):
                        attempts += 1
                        time.sleep(0.5)
                        continue
                    return GeminiRawOutput(error=self._describe_error(exc), provider="gemini")
        except Exception as exc:
            return GeminiRawOutput(error=self._describe_error(exc), provider="gemini")

    def _generate_once(
        self,
        contents: Any,
        system_instruction: str | None,
        tool_defs: Any,
        temperature: float,
        max_output_tokens: int,
        response_json: bool,
    ) -> Any:
        types = self._types
        config: dict[str, Any] = {"temperature": temperature, "max_output_tokens": max_output_tokens}
        if system_instruction:
            config["system_instruction"] = system_instruction
        if response_json:
            config["response_mime_type"] = "application/json"
        if tool_defs:
            config["tools"] = tool_defs
        return self._client.models.generate_content(
            model=self.model, contents=contents, config=types.GenerateContentConfig(**config)
        )

    def _build_tools(self, declarations: list[dict[str, Any]] | None) -> Any:
        if not declarations:
            return None
        types = self._types
        function_declarations = [
            types.FunctionDeclaration(
                name=declaration["name"],
                description=declaration.get("description", ""),
                parameters=types.Schema(**declaration.get("parameters", {})),
            )
            for declaration in declarations
        ]
        return [types.Tool(function_declarations=function_declarations)]

    def _content(self, message: dict[str, Any]) -> Any:
        types = self._types
        role = message.get("role", "user")
        if role == "function":
            role = "user"
        parts: list[Any] = []
        for part in message.get("parts", []):
            if part.get("text"):
                parts.append(types.Part(text=part["text"]))
            if part.get("function_call"):
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=part["function_call"]["name"],
                            args=part["function_call"].get("args", {}),
                        )
                    )
                )
            if part.get("function_response"):
                response = part["function_response"]
                parts.append(
                    types.Part.from_function_response(name=response["name"], response=response["response"])
                )
        return types.Content(role=role, parts=parts)

    def _extract(self, response: Any) -> GeminiRawOutput:
        text: str | None = None
        tool_calls: list[ToolCall] = []
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", None) or []:
                function_call = getattr(part, "function_call", None)
                if function_call is not None:
                    tool_calls.append(ToolCall(name=function_call.name, args=self._coerce_args(function_call.args)))
                elif getattr(part, "text", None):
                    if text is None:
                        text = part.text
        if text is None and not tool_calls:
            return GeminiRawOutput(error="EMPTY_RESPONSE")
        return GeminiRawOutput(text=text, tool_calls=tool_calls)

    @staticmethod
    def _coerce_args(args: Any) -> dict[str, Any]:
        if args is None:
            return {}
        if isinstance(args, dict):
            return dict(args)
        if isinstance(args, str):
            try:
                return json.loads(args) if args else {}
            except Exception:
                return {"arguments": args}
        try:
            from google.protobuf.json_format import MessageToDict
            return dict(MessageToDict(args))
        except Exception:
            return dict(args)

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        name = type(exc).__name__
        code = getattr(exc, "code", None)
        return name in {
            "RateLimitError",
            "InternalServerError",
            "ServiceUnavailable",
            "APITimeoutError",
        } or (isinstance(code, int) and code in {429, 500, 502, 503, 504})

    @staticmethod
    def _describe_error(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"