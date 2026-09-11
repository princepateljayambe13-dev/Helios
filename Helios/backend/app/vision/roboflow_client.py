"""Lightweight HTTP client for Roboflow serverless APIs with local fallback support.

Works across all Python versions (including Python 3.14+) using standard HTTP requests,
removing reliance on inference-sdk.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)


class RoboflowHttpClient:
    """Performs inference against Roboflow Serverless REST endpoints without inference-sdk."""

    def __init__(self, api_url: str = "https://serverless.roboflow.com", api_key: str = "") -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=10.0)
        self._auth_failed: set[str] = set()

    def infer(self, image_path: str | Path, model_id: str) -> dict[str, Any]:
        """Call object detection endpoint with image file."""
        if model_id in self._auth_failed:
            return {"predictions": []}

        path = Path(image_path)
        if not path.exists():
            return {"predictions": []}

        url = f"{self.api_url}/{model_id.lstrip('/')}"
        params = {"api_key": self.api_key}
        headers = {"Authorization": f"Bearer {self.api_key}", "api-key": self.api_key}

        try:
            with open(path, "rb") as f:
                image_data = f.read()
            response = self._client.post(
                url,
                params=params,
                headers=headers,
                files={"file": (path.name, image_data, "image/jpeg")},
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 401:
                self._auth_failed.add(model_id)
                LOGGER.warning("Roboflow 401 Unauthorized for model '%s'. Check UAV_ROBOFLOW_API_KEY. Falling back to local standby.", model_id)
                return {"predictions": []}
            if response.status_code == 402:
                self._auth_failed.add(model_id)
                LOGGER.warning("Roboflow 402 Payment Required for model '%s'. Serverless inference credit cap exceeded. Falling back to local standby.", model_id)
                return {"predictions": []}
            LOGGER.warning("Roboflow infer call returned status %s: %s", response.status_code, response.text[:200])
            return {"predictions": []}
        except Exception as err:
            LOGGER.warning("Roboflow infer request failed: %s", err)
            return {"predictions": []}

    def run_workflow(
        self,
        workspace_name: str,
        workflow_id: str,
        images: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> Any:
        """Call Roboflow Workflows endpoint."""
        target_key = f"{workspace_name}/{workflow_id}"
        if target_key in self._auth_failed:
            return [{"model_predictions": {"predictions": []}}]

        url = f"{self.api_url}/infer/workflows/{workspace_name}/{workflow_id}"
        params = {"api_key": self.api_key}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        image_inputs: dict[str, Any] = {}
        for key, val in images.items():
            val_path = Path(val)
            if val_path.exists():
                with open(val_path, "rb") as f:
                    image_inputs[key] = {"type": "base64", "value": base64.b64encode(f.read()).decode("utf-8")}
            else:
                image_inputs[key] = val

        all_inputs: dict[str, Any] = dict(image_inputs)
        if parameters:
            for p_key, p_val in parameters.items():
                if p_key not in all_inputs:
                    all_inputs[p_key] = p_val if isinstance(p_val, (list, dict)) else [p_val]

        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "inputs": all_inputs,
            "parameters": parameters or {},
            "use_cache": use_cache,
        }

        try:
            response = self._client.post(url, params=params, headers=headers, json=payload)
            if response.status_code == 404:
                alt_url = f"{self.api_url}/{workspace_name}/workflows/{workflow_id}"
                response = self._client.post(alt_url, params=params, headers=headers, json=payload)
                if response.status_code == 404:
                    self._auth_failed.add(target_key)
                    LOGGER.warning(
                        "Roboflow 404 Not Found for workspace '%s', workflow '%s'. Make sure workspace_name and workflow_id in config/models.yaml match your Roboflow account. Falling back to local standby.",
                        workspace_name,
                        workflow_id,
                    )
                    return [{"model_predictions": {"predictions": []}}]
            if response.status_code == 200:
                return response.json()
            if response.status_code == 401:
                self._auth_failed.add(target_key)
                LOGGER.warning(
                    "Roboflow 401 Unauthorized for workspace '%s', workflow '%s'. Check that UAV_ROBOFLOW_API_KEY is valid for '%s'. Falling back to local standby.",
                    workspace_name,
                    workflow_id,
                    workspace_name,
                )
                return [{"model_predictions": {"predictions": []}}]
            if response.status_code == 402:
                self._auth_failed.add(target_key)
                LOGGER.warning(
                    "Roboflow 402 Payment Required / credit_cap_exceeded for workspace '%s', workflow '%s'. Serverless inference credit limit reached on Roboflow account. Falling back to local standby.",
                    workspace_name,
                    workflow_id,
                )
                return [{"model_predictions": {"predictions": []}}]
            LOGGER.warning("Roboflow workflow call returned status %s: %s", response.status_code, response.text[:200])
            return [{"predictions": []}]
        except Exception as err:
            LOGGER.warning("Roboflow workflow request failed: %s", err)
            return [{"predictions": []}]

    def close(self) -> None:
        self._client.close()


class LocalFallbackClient:
    """Local fallback detector client when no Roboflow API key is provided."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def infer(self, image_path: str | Path, model_id: str) -> dict[str, Any]:
        """Return empty predictions safely in local fallback mode."""
        return {"predictions": []}

    def run_workflow(
        self,
        workspace_name: str,
        workflow_id: str,
        images: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> Any:
        """Return empty workflow predictions safely in local fallback mode."""
        return [{"model_predictions": {"predictions": []}}]

    def close(self) -> None:
        pass
