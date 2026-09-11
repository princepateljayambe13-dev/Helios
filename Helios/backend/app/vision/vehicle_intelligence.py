"""Vehicle Intelligence module for HELIOS.

Provides:
- VehicleClassifier: Pluggable Hugging Face Transformers CLIP zero-shot classification interface
  Target model: openai/clip-vit-base-patch32
  Categories: SUV, pickup truck, hatchback, taxi, sedan, heavy truck
- VehicleColorDetector: OpenCV-based HSV color detection for vehicle crops
- VehicleIntelligencePipeline: Orchestrates vehicle crop extraction, CLIP classification,
  and color detection into a unified vehicle intelligence record.
"""
from __future__ import annotations

import logging
import time
from typing import Any

LOGGER = logging.getLogger(__name__)

# Standard vehicle classification categories
VEHICLE_TYPES = [
    "SUV",
    "pickup truck",
    "hatchback",
    "taxi",
    "sedan",
    "heavy truck",
    "van",
    "minivan",
    "bus",
    "motorcycle",
    "bicycle",
    "emergency vehicle",
    "delivery truck",
]

# Descriptive prompts for zero-shot classification
VEHICLE_TYPE_PROMPTS = [
    "a photo of an SUV",
    "a photo of a pickup truck",
    "a photo of a hatchback",
    "a photo of a taxi",
    "a photo of a sedan",
    "a photo of a heavy truck",
    "a photo of a van",
    "a photo of a minivan",
    "a photo of a bus",
    "a photo of a motorcycle",
    "a photo of a bicycle",
    "a photo of an emergency vehicle",
    "a photo of a delivery truck",
]

# Standard vehicle colors for zero-shot CLIP classification
VEHICLE_COLORS = [
    "black",
    "white",
    "gray",
    "silver",
    "red",
    "blue",
    "green",
    "yellow",
    "brown",
    "orange",
]

VEHICLE_COLOR_PROMPTS = [f"a photo of a {color} vehicle" for color in VEHICLE_COLORS]

CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"


def _resolve_device(device_pref: str = "auto") -> str | int:
    """Resolve compute device: prefers Apple Silicon Metal (mps), then CUDA, then CPU."""
    if device_pref != "auto":
        return device_pref
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return 0
    except Exception:
        pass
    return "cpu"


def _to_pil_image(image: Any) -> Any:
    """Safely convert numpy BGR or bytes image into a PIL Image."""
    if image is None:
        return None
    try:
        from PIL import Image
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        import numpy as np
        if isinstance(image, np.ndarray):
            if image.size == 0:
                return None
            import cv2
            if len(image.shape) == 3 and image.shape[2] == 3:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                return Image.fromarray(rgb)
            return Image.fromarray(image).convert("RGB")
        if isinstance(image, (bytes, bytearray)):
            import io
            return Image.open(io.BytesIO(image)).convert("RGB")
    except Exception as exc:
        LOGGER.debug("Could not convert image to PIL Image: %s", exc)
    return None


class ClipPipelineManager:
    """Shared singleton manager for Hugging Face Transformers zero-shot classification pipeline.

    Ensures openai/clip-vit-base-patch32 is loaded into unified memory/MPS only once,
    avoiding memory duplication and latency spikes.
    """
    _pipeline_instance: Any | None = None
    _attempted_load: bool = False

    @classmethod
    def get_pipeline(cls, model_name: str = CLIP_MODEL_NAME, device: str = "auto") -> Any | None:
        if cls._pipeline_instance is not None:
            return cls._pipeline_instance
        if cls._attempted_load:
            return None

        cls._attempted_load = True
        try:
            import os
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub/models--openai--clip-vit-base-patch32")
            if os.path.exists(cache_dir):
                os.environ.setdefault("HF_HUB_OFFLINE", "1")

            from transformers import pipeline
            resolved_dev = _resolve_device(device)
            LOGGER.info("Loading CLIP model=%s on device=%s", model_name, resolved_dev)
            cls._pipeline_instance = pipeline(
                "zero-shot-image-classification",
                model=model_name,
                device=resolved_dev,
            )
            return cls._pipeline_instance
        except ImportError:
            LOGGER.info(
                "Transformers or torch not installed. Running CLIP classification in dormant mode. "
                "Run 'pip install transformers torch pillow' to activate."
            )
            cls._pipeline_instance = None
            return None
        except Exception as exc:
            LOGGER.warning("Could not initialize CLIP pipeline: %s", exc)
            cls._pipeline_instance = None
            return None

    @classmethod
    def set_pipeline(cls, pipeline_instance: Any | None) -> None:
        """Inject a mock or custom pipeline instance (useful for unit tests)."""
        cls._pipeline_instance = pipeline_instance
        cls._attempted_load = pipeline_instance is not None

    @classmethod
    def reset(cls) -> None:
        cls._pipeline_instance = None
        cls._attempted_load = False


class VehicleClassifier:
    """CLIP vehicle-type classifier interface for HELIOS.

    Uses Hugging Face Transformers zero-shot image classification with
    openai/clip-vit-base-patch32 when dependencies are installed.
    Gracefully returns None if transformers/torch is unavailable or not yet connected.
    """

    def __init__(
        self,
        model_name: str = CLIP_MODEL_NAME,
        candidate_labels: list[str] | None = None,
        confidence_threshold: float = 0.30,
        device: str = "auto",
        pipeline_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.candidate_labels = candidate_labels or list(VEHICLE_TYPES)
        self.confidence_threshold = confidence_threshold
        self.device_preference = device
        self._custom_pipeline = pipeline_instance

    def _resolve_device(self) -> str | int:
        return _resolve_device(self.device_preference)

    def is_available(self) -> bool:
        """Check whether transformers and torch dependencies are installed."""
        if self._custom_pipeline is False:
            return False
        if self._custom_pipeline is not None or ClipPipelineManager._pipeline_instance is not None:
            return True
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    def _load_pipeline(self) -> Any:
        if self._custom_pipeline is False:
            return None
        if self._custom_pipeline is not None:
            return self._custom_pipeline
        return ClipPipelineManager.get_pipeline(self.model_name, self.device_preference)

    def classify(self, image: Any) -> dict[str, Any]:
        """Classify a vehicle crop using CLIP zero-shot image classification.

        Args:
            image: Cropped vehicle image (numpy BGR, PIL Image, or JPEG bytes).

        Returns:
            Dict containing:
                "type": Best category label (e.g. "sedan") or None if unavailable/low confidence.
                "type_confidence": Confidence score between 0.0 and 1.0, or None.
                "raw_scores": Dict mapping categories to confidence scores, or None.
                "is_low_confidence": Boolean indicating whether top confidence is below threshold.
        """
        pipe = self._load_pipeline()
        if pipe is None:
            return {
                "type": None,
                "type_confidence": None,
                "raw_scores": None,
                "is_low_confidence": False,
            }

        pil_image = _to_pil_image(image)
        if pil_image is None:
            return {
                "type": None,
                "type_confidence": None,
                "raw_scores": None,
                "is_low_confidence": False,
            }

        try:
            results = pipe(
                pil_image,
                candidate_labels=self.candidate_labels,
                hypothesis_template="a photo of a {}",
            )
            if not results:
                return {
                    "type": None,
                    "type_confidence": None,
                    "raw_scores": None,
                    "is_low_confidence": False,
                }

            # Results are list of {"label": str, "score": float} sorted by score descending
            top = results[0]
            top_label = str(top["label"]).lower()
            top_score = round(float(top["score"]), 2)
            raw_scores = {str(r["label"]).lower(): round(float(r["score"]), 3) for r in results}

            if top_score < self.confidence_threshold:
                return {
                    "type": "unknown",
                    "type_confidence": top_score,
                    "raw_scores": raw_scores,
                    "is_low_confidence": True,
                }

            return {
                "type": top_label,
                "type_confidence": top_score,
                "raw_scores": raw_scores,
                "is_low_confidence": False,
            }
        except Exception as exc:
            LOGGER.warning("CLIP vehicle classification failed: %s", exc)
            return {
                "type": None,
                "type_confidence": None,
                "raw_scores": None,
                "is_low_confidence": False,
            }

    def classify_heuristic(
        self,
        image: Any = None,
        bounding_box: list[float] | None = None,
        source_class: str | None = None,
    ) -> dict[str, Any]:
        """Heuristic rule-based vehicle classification for local / offline operation.

        Evaluates detector source class hints and bounding box aspect ratios.
        """
        source = (source_class or "").strip().lower()
        if source == "motorcycle":
            return {"type": "motorcycle", "type_confidence": 0.88, "raw_scores": {"motorcycle": 0.88}, "is_low_confidence": False}
        if source == "bicycle":
            return {"type": "bicycle", "type_confidence": 0.88, "raw_scores": {"bicycle": 0.88}, "is_low_confidence": False}
        if source == "bus":
            return {"type": "bus", "type_confidence": 0.90, "raw_scores": {"bus": 0.90}, "is_low_confidence": False}
        if source in ("van", "minivan"):
            return {"type": "van", "type_confidence": 0.85, "raw_scores": {"van": 0.85}, "is_low_confidence": False}
        if source == "pickup":
            return {"type": "pickup truck", "type_confidence": 0.85, "raw_scores": {"pickup truck": 0.85}, "is_low_confidence": False}
        if source == "suv":
            return {"type": "SUV", "type_confidence": 0.85, "raw_scores": {"suv": 0.85}, "is_low_confidence": False}
        if source == "truck":
            return {"type": "truck", "type_confidence": 0.85, "raw_scores": {"truck": 0.85}, "is_low_confidence": False}

        # Bounding box geometry heuristic
        aspect_ratio = None
        if bounding_box and len(bounding_box) == 4:
            bw, bh = float(bounding_box[2]), float(bounding_box[3])
            if bh > 0:
                aspect_ratio = bw / bh
        elif image is not None:
            try:
                import numpy as np
                if isinstance(image, np.ndarray) and image.shape[0] > 0 and image.shape[1] > 0:
                    aspect_ratio = float(image.shape[1]) / float(image.shape[0])
            except Exception:
                pass

        if aspect_ratio is not None:
            if aspect_ratio < 0.65:
                return {"type": "motorcycle", "type_confidence": 0.72, "raw_scores": {"motorcycle": 0.72}, "is_low_confidence": False}
            if aspect_ratio > 2.2:
                vtype = "heavy truck" if source == "truck" else "bus"
                return {"type": vtype, "type_confidence": 0.75, "raw_scores": {vtype: 0.75}, "is_low_confidence": False}
            if aspect_ratio > 1.7:
                vtype = "pickup truck" if source == "truck" else "sedan"
                return {"type": vtype, "type_confidence": 0.72, "raw_scores": {vtype: 0.72}, "is_low_confidence": False}
            if aspect_ratio >= 1.2:
                return {"type": "SUV", "type_confidence": 0.70, "raw_scores": {"suv": 0.70}, "is_low_confidence": False}
            if aspect_ratio >= 0.9:
                return {"type": "hatchback", "type_confidence": 0.68, "raw_scores": {"hatchback": 0.68}, "is_low_confidence": False}

        if source == "truck":
            return {"type": "heavy truck", "type_confidence": 0.78, "raw_scores": {"heavy truck": 0.78}, "is_low_confidence": False}
        if source == "car":
            return {"type": "sedan", "type_confidence": 0.70, "raw_scores": {"sedan": 0.70}, "is_low_confidence": False}

        return {"type": None, "type_confidence": None, "raw_scores": None, "is_low_confidence": False}


class VehicleColorClassifier:
    """CLIP zero-shot vehicle color classifier for HELIOS.

    Replaces OpenCV color detection. Evaluates cropped vehicle image with:
      candidate_labels = [f"a photo of a {color} vehicle" for color in colors]
    And parses pure color labels (e.g. "blue", "red", "silver").
    """

    def __init__(
        self,
        model_name: str = CLIP_MODEL_NAME,
        colors: list[str] | None = None,
        confidence_threshold: float = 0.15,
        device: str = "auto",
        pipeline_instance: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.colors = colors or list(VEHICLE_COLORS)
        self.labels = [f"a photo of a {c} vehicle" for c in self.colors]
        self.confidence_threshold = confidence_threshold
        self.device = device
        self._custom_pipeline = pipeline_instance

    def is_available(self) -> bool:
        """Check whether transformers and torch dependencies are installed."""
        if self._custom_pipeline is False:
            return False
        if self._custom_pipeline is not None or ClipPipelineManager._pipeline_instance is not None:
            return True
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_pipeline(self) -> Any | None:
        if self._custom_pipeline is False:
            return None
        if self._custom_pipeline is not None:
            return self._custom_pipeline
        return ClipPipelineManager.get_pipeline(self.model_name, self.device)

    def classify_color(self, image: Any) -> dict[str, Any]:
        """Classify vehicle color using CLIP.

        Returns:
            Dict with keys:
                "color": Best color string (e.g. "blue") or None if dormant.
                "color_confidence": Float confidence score between 0.0 and 1.0.
                "color_scores": Dict mapping each color to its normalized score.
                "is_low_confidence": Boolean.
        """
        pipe = self._get_pipeline()
        if pipe is None:
            return {
                "color": None,
                "color_confidence": None,
                "color_scores": {},
                "is_low_confidence": False,
            }

        pil_image = _to_pil_image(image)
        if pil_image is None:
            return {
                "color": None,
                "color_confidence": None,
                "color_scores": {},
                "is_low_confidence": False,
            }

        try:
            results = pipe(pil_image, candidate_labels=self.labels)
            if not results:
                return {
                    "color": None,
                    "color_confidence": None,
                    "color_scores": {},
                    "is_low_confidence": False,
                }

            color_scores: dict[str, float] = {}
            for r in results:
                raw_label = str(r["label"]).lower()
                clean_color = (
                    raw_label.replace("a photo of a ", "")
                    .replace(" vehicle", "")
                    .strip()
                )
                color_scores[clean_color] = float(r["score"])

            best = results[0]
            best_color = (
                str(best["label"])
                .replace("a photo of a ", "")
                .replace(" vehicle", "")
                .strip()
                .lower()
            )
            score = round(float(best["score"]), 2)

            if score < self.confidence_threshold:
                return {
                    "color": "unknown",
                    "color_confidence": score,
                    "color_scores": color_scores,
                    "is_low_confidence": True,
                }

            return {
                "color": best_color,
                "color_confidence": score,
                "color_scores": color_scores,
                "is_low_confidence": False,
            }
        except Exception as exc:
            LOGGER.warning("CLIP vehicle color classification failed: %s", exc)
            return {
                "color": None,
                "color_confidence": None,
                "color_scores": {},
                "is_low_confidence": False,
            }


class TrackColorState:
    """State tracking color distributions and stability for a specific vehicle track."""

    def __init__(self, track_id: str) -> None:
        self.track_id: str = track_id
        self.observation_count: int = 0
        self.color_scores: dict[str, float] = {}
        self.stabilized_color: str | None = None
        self.stabilized_confidence: float | None = None
        self.consecutive_stable: int = 0
        self.last_inference_time: float = 0.0

        # Type stabilization
        self.type_scores: dict[str, float] = {}
        self.stabilized_type: str | None = None
        self.stabilized_type_confidence: float | None = None


class TrackColorStabilizer:
    """Temporal color stabilizer for tracked vehicles.

    Associates classifications with the tracked vehicle ID, accumulates observation
    probabilities via Exponential Moving Average (EMA), eliminates single-frame
    flickering/lighting noise, and provides high-speed caching for zero-lag streaming.
    """

    def __init__(
        self,
        alpha: float = 0.35,
        min_interval_seconds: float = 0.10,
        convergence_threshold: float = 0.75,
        convergence_min_frames: int = 3,
    ) -> None:
        self.alpha = alpha
        self.min_interval_seconds = min_interval_seconds
        self.convergence_threshold = convergence_threshold
        self.convergence_min_frames = convergence_min_frames
        self._tracks: dict[str, TrackColorState] = {}

    def get_state(self, track_id: str) -> TrackColorState:
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackColorState(track_id)
        return self._tracks[track_id]

    def should_run_inference(self, track_id: str, current_time: float | None = None) -> bool:
        """Determines if a forward pass is needed or if stabilized result can be returned immediately.

        Ensures zero-lag video pipeline operation on high-FPS streams.
        """
        now_ts = current_time if current_time is not None else time.monotonic()
        state = self.get_state(track_id)
        if state.observation_count == 0:
            return True

        # If stabilized with high confidence, sample periodically instead of every frame
        if (
            state.observation_count >= self.convergence_min_frames
            and (state.stabilized_confidence or 0.0) >= self.convergence_threshold
            and state.consecutive_stable >= 3
        ):
            # Sample every 10 frames or 1.0s, returning cached stabilized result on intermediate frames
            if state.observation_count % 10 != 0 and (now_ts - state.last_inference_time) < 1.0:
                return False

        # Throttle frames closer than min_interval_seconds
        if (now_ts - state.last_inference_time) < self.min_interval_seconds:
            return False

        return True

    def stabilize_color(
        self,
        track_id: str,
        color_scores: dict[str, float],
        current_time: float | None = None,
    ) -> tuple[str | None, float | None]:
        """Update temporal distribution and return stabilized color and confidence."""
        state = self.get_state(track_id)
        if not color_scores:
            return state.stabilized_color, state.stabilized_confidence

        now_ts = current_time if current_time is not None else time.monotonic()
        state.last_inference_time = now_ts
        state.observation_count += 1

        if not state.color_scores:
            state.color_scores = dict(color_scores)
        else:
            # EMA smoothing across candidate colors
            for col, score in color_scores.items():
                prev = state.color_scores.get(col, score)
                state.color_scores[col] = self.alpha * score + (1.0 - self.alpha) * prev

        best_col, best_score = max(state.color_scores.items(), key=lambda x: x[1])
        new_color = best_col
        new_conf = round(float(best_score), 2)

        if new_color == state.stabilized_color:
            state.consecutive_stable += 1
        else:
            state.consecutive_stable = 1

        state.stabilized_color = new_color
        state.stabilized_confidence = new_conf

        return state.stabilized_color, state.stabilized_confidence

    def stabilize_type(
        self,
        track_id: str,
        type_scores: dict[str, float] | None,
        top_type: str | None,
        top_conf: float | None,
    ) -> tuple[str | None, float | None]:
        """Optionally stabilize vehicle type across observations."""
        state = self.get_state(track_id)
        if top_type is None:
            return state.stabilized_type, state.stabilized_type_confidence

        if not state.stabilized_type or (top_conf and top_conf > (state.stabilized_type_confidence or 0.0)):
            state.stabilized_type = top_type
            state.stabilized_type_confidence = top_conf

        return state.stabilized_type, state.stabilized_type_confidence

    def remove_track(self, track_id: str) -> None:
        self._tracks.pop(track_id, None)

    def prune_stale(self, active_track_ids: set[str]) -> None:
        to_remove = [tid for tid in self._tracks if tid not in active_track_ids]
        for tid in to_remove:
            self._tracks.pop(tid, None)


class VehicleColorDetector:
    """Backward-compatible OpenCV HSV detector wrapper.

    Provided for backward compatibility with legacy tests or environments
    where OpenCV color fallback is explicitly queried.
    """

    COLOR_RANGES = {
        "black": [{"lower": (0, 0, 0), "upper": (180, 100, 55)}],
        "white": [{"lower": (0, 0, 185), "upper": (180, 45, 255)}],
        "gray": [{"lower": (0, 0, 65), "upper": (180, 55, 185)}],
        "red": [{"lower": (0, 60, 55), "upper": (10, 255, 255)}, {"lower": (170, 60, 55), "upper": (180, 255, 255)}],
        "orange": [{"lower": (11, 60, 65), "upper": (22, 255, 255)}],
        "yellow": [{"lower": (23, 60, 65), "upper": (35, 255, 255)}],
        "green": [{"lower": (36, 50, 50), "upper": (85, 255, 255)}],
        "blue": [{"lower": (90, 50, 50), "upper": (135, 255, 255)}],
        "brown": [{"lower": (10, 50, 40), "upper": (25, 200, 110)}],
    }

    def __init__(self, confidence_threshold: float = 0.20) -> None:
        self.confidence_threshold = confidence_threshold

    def detect_color(self, image: Any) -> dict[str, Any]:
        if image is None:
            return {"color": "unknown", "color_confidence": 0.0, "is_low_confidence": True}
        try:
            import cv2
            import numpy as np

            if not isinstance(image, np.ndarray) or image.size == 0:
                return {"color": "unknown", "color_confidence": 0.0, "is_low_confidence": True}

            h, w = image.shape[:2]
            if h < 5 or w < 5:
                return {"color": "unknown", "color_confidence": 0.0, "is_low_confidence": True}

            y1, y2 = int(h * 0.15), max(int(h * 0.15) + 2, int(h * 0.85))
            x1, x2 = int(w * 0.10), max(int(w * 0.10) + 2, int(w * 0.90))
            roi = image[y1:y2, x1:x2]
            hsv = cv2.cvtColor(cv2.GaussianBlur(roi, (5, 5), 0), cv2.COLOR_BGR2HSV)
            total_pixels = max(1, roi.shape[0] * roi.shape[1])

            color_scores: dict[str, int] = {}
            for color_name, ranges in self.COLOR_RANGES.items():
                mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
                for r in ranges:
                    range_mask = cv2.inRange(hsv, np.array(r["lower"], dtype=np.uint8), np.array(r["upper"], dtype=np.uint8))
                    mask = cv2.bitwise_or(mask, range_mask)
                color_scores[color_name] = int(cv2.countNonZero(mask))

            top_color, top_count = sorted(color_scores.items(), key=lambda x: x[1], reverse=True)[0]
            classified_pixels = sum(color_scores.values())
            if classified_pixels > 0:
                dominance = top_count / classified_pixels
                coverage = top_count / total_pixels
                confidence = round(min(0.99, max(0.40, dominance * 0.65 + coverage * 0.35 + 0.15)), 2)
            else:
                top_color = "unknown"
                confidence = 0.0

            if confidence < self.confidence_threshold or top_count < 10:
                return {"color": "unknown", "color_confidence": confidence, "is_low_confidence": True}
            return {"color": top_color, "color_confidence": confidence, "is_low_confidence": False}
        except Exception as exc:
            LOGGER.warning("OpenCV vehicle color detection failed: %s", exc)
            return {"color": "unknown", "color_confidence": 0.0, "is_low_confidence": True}


class VehicleIntelligencePipeline:
    """Unified vehicle intelligence pipeline with temporal stabilization.

    Coordinates vehicle bounding-box cropping, CLIP vehicle-type classification,
    CLIP vehicle-color classification, and temporal stabilization across track observations.
    """

    def __init__(
        self,
        classifier: VehicleClassifier | None = None,
        color_classifier: VehicleColorClassifier | None = None,
        color_detector: Any | None = None,
        stabilizer: TrackColorStabilizer | None = None,
        shared_pipeline: Any | None = None,
        enable_heuristics: bool = False,
    ) -> None:
        if shared_pipeline is not None:
            ClipPipelineManager.set_pipeline(shared_pipeline)

        self.classifier = classifier or VehicleClassifier()
        # Prefer color_classifier (CLIP), or adapt custom pipeline
        custom_pipe = getattr(self.classifier, "_custom_pipeline", None)
        self.color_classifier = color_classifier or VehicleColorClassifier(
            pipeline_instance=custom_pipe
        )
        self.color_detector = color_detector  # Optional legacy fallback
        self.stabilizer = stabilizer or TrackColorStabilizer()
        self.enable_heuristics = enable_heuristics

    def crop_vehicle(self, image: Any, bounding_box: list[float] | None = None) -> Any:
        """Crop the vehicle region from a normalized bounding box [x, y, w, h]."""
        if image is None:
            return None
        if bounding_box and len(bounding_box) == 4:
            try:
                import numpy as np
                if isinstance(image, np.ndarray):
                    h, w = image.shape[:2]
                    x, y, bw, bh = (float(v) for v in bounding_box)
                    x1 = max(0, min(w - 1, int(round(x * w))))
                    y1 = max(0, min(h - 1, int(round(y * h))))
                    x2 = max(x1 + 1, min(w, int(round((x + bw) * w))))
                    y2 = max(y1 + 1, min(h, int(round((y + bh) * h))))
                    if x2 > x1 and y2 > y1:
                        crop = image[y1:y2, x1:x2]
                        if crop.size > 0:
                            return crop
            except Exception:
                pass
        return image

    def analyze_vehicle(
        self,
        image: Any,
        bounding_box: list[float] | None = None,
        vehicle_id: str = "V-001",
        source_class: str | None = None,
        enable_heuristics: bool | None = None,
    ) -> dict[str, Any]:
        """Analyze a vehicle detection and return a temporally stabilized vehicle intelligence record.

        Fast path: If the track has already converged on high confidence, immediately
        returns the stabilized prediction without blocking the video pipeline.
        """
        use_heuristics = self.enable_heuristics if enable_heuristics is None else enable_heuristics
        crop = self.crop_vehicle(image, bounding_box)
        norm_id = vehicle_id.lstrip("#") if vehicle_id else "V-001"
        track_key = vehicle_id or "V-001"

        state = self.stabilizer.get_state(track_key)

        # Fast-path check: avoid re-running CLIP on rapid identical frames
        if (
            state.stabilized_color is not None
            and state.stabilized_type is not None
            and not self.stabilizer.should_run_inference(track_key)
        ):
            return {
                "vehicle_id": norm_id,
                "type": state.stabilized_type,
                "type_confidence": state.stabilized_type_confidence,
                "color": state.stabilized_color,
                "color_confidence": state.stabilized_confidence,
            }

        # 1. CLIP vehicle-type classification
        classification = self.classifier.classify(crop)
        veh_type = classification.get("type")
        type_conf = classification.get("type_confidence")
        type_scores = classification.get("raw_scores")

        # Fallback to heuristic classification if CLIP is dormant or returned None and heuristics enabled
        if veh_type is None and use_heuristics and hasattr(self.classifier, "classify_heuristic"):
            heuristic_res = self.classifier.classify_heuristic(crop, bounding_box=bounding_box, source_class=source_class)
            if heuristic_res.get("type"):
                veh_type = heuristic_res["type"]
                type_conf = heuristic_res.get("type_confidence")
                type_scores = heuristic_res.get("raw_scores")

        # Stabilize type across observations
        stab_type, stab_type_conf = self.stabilizer.stabilize_type(
            track_key, type_scores, veh_type, type_conf
        )

        # 2. CLIP vehicle-color classification
        color_result = self.color_classifier.classify_color(crop)
        color = color_result.get("color")
        color_conf = color_result.get("color_confidence")
        color_scores = color_result.get("color_scores", {})

        # If CLIP is dormant but a legacy OpenCV detector is present, fallback
        if color is None and self.color_detector is not None:
            cv_res = self.color_detector.detect_color(crop)
            color = cv_res.get("color")
            color_conf = cv_res.get("color_confidence")
            if color and color != "unknown":
                color_scores = {color: color_conf or 0.8}

        # 3. Track-level temporal color stabilization across observations
        stab_color, stab_color_conf = self.stabilizer.stabilize_color(
            track_key, color_scores
        )

        return {
            "vehicle_id": norm_id,
            "type": stab_type or veh_type,
            "type_confidence": stab_type_conf or type_conf,
            "color": stab_color or color,
            "color_confidence": stab_color_conf or color_conf,
        }
