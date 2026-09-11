"""Lightweight Computer-Vision Metrics and Condition Classifier for CCTV Feeds.

Continuously evaluates CCTV frames to detect visual degradations:
- DEAD_FEED (whole black / dead feed)
- FULL_WHITE_OVEREXPOSURE (full white / blinded)
- PARTIAL_WHITE_OVEREXPOSURE (glare / localized overexposure)
- BLURRED (out of focus / blurred dome)
- LOW_CONTRAST (opaque / low contrast / flat)
- FOG_HAZE (fog / haze / smoke)
- HEAVY_RAIN (vertical rain streaks and temporal flutter)
- OBSTRUCTED (physical blockage / covered lens)
- CLEAR (normal clear visibility)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class CameraMetrics:
    """Quantitative computer-vision metrics extracted from a single video frame."""

    brightness: float          # Mean luminance [0, 255]
    brightness_p5: float       # 5th percentile luminance
    brightness_p95: float      # 95th percentile luminance
    contrast: float            # Standard deviation of luminance [0, 128]
    laplacian_variance: float  # Variance of Laplacian (focus/blur metric)
    white_pixel_ratio: float   # Ratio of pixels with Y > 245 [0.0, 1.0]
    edge_density: float        # Ratio of Canny edge pixels [0.0, 1.0]
    frame_difference: float    # Mean absolute difference from previous frame [0, 255]
    vertical_edge_ratio: float # Ratio of vertical to horizontal edge strength
    patch_occlusion_ratio: float # Fraction of spatial patches with zero texture [0.0, 1.0]

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in asdict(self).items()}


@dataclass
class DetectionResult:
    """Raw single-frame classification before temporal hysteresis confirmation."""

    condition: str
    confidence: float
    reliability_score: int     # 0 to 100
    metrics: CameraMetrics
    reason: str


class CameraVisibilityDetector:
    """Computes vision metrics and classifies frame visual quality."""

    # Default reliability score assignments
    RELIABILITY_SCORES = {
        "CLEAR": 100,
        "HEAVY_RAIN": 75,
        "FOG_HAZE": 70,
        "PARTIAL_WHITE_OVEREXPOSURE": 65,
        "LOW_CONTRAST": 50,
        "BLURRED": 40,
        "OBSTRUCTED": 20,
        "FULL_WHITE_OVEREXPOSURE": 10,
        "DEAD_FEED": 5,
    }

    @classmethod
    def calculate_metrics(
        cls,
        image: np.ndarray,
        prev_image: np.ndarray | None = None,
    ) -> CameraMetrics:
        """Extract lightweight vision metrics from an RGB or BGR OpenCV image."""
        if image is None or image.size == 0:
            return CameraMetrics(
                brightness=0.0,
                brightness_p5=0.0,
                brightness_p95=0.0,
                contrast=0.0,
                laplacian_variance=0.0,
                white_pixel_ratio=0.0,
                edge_density=0.0,
                frame_difference=0.0,
                vertical_edge_ratio=1.0,
                patch_occlusion_ratio=1.0,
            )

        # Convert to grayscale
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        h, w = gray.shape[:2]
        total_pixels = max(1, h * w)

        # Downscale for ultra-fast metric calculation if frame is large
        if w > 640:
            scale = 640.0 / w
            gray_small = cv2.resize(gray, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            gray_small = gray

        small_pixels = gray_small.shape[0] * gray_small.shape[1]

        # 1. Brightness & Percentiles
        brightness = float(np.mean(gray_small))
        p5, p95 = np.percentile(gray_small, [5, 95])

        # 2. Contrast (standard deviation)
        contrast = float(np.std(gray_small))

        # 3. Laplacian Variance (Focus / Blur)
        lap = cv2.Laplacian(gray_small, cv2.CV_64F)
        laplacian_var = float(lap.var())

        # 4. White-Pixel Ratio (pixels > 245)
        white_pixels = int(np.count_nonzero(gray_small >= 245))
        white_ratio = float(white_pixels / small_pixels)

        # 5. Edge Density (Canny)
        edges = cv2.Canny(gray_small, 50, 150)
        edge_pixels = int(np.count_nonzero(edges))
        edge_density = float(edge_pixels / small_pixels)

        # 6. Vertical vs Horizontal Edge Energy (Sobel for rain streak detection)
        sobel_x = cv2.Sobel(gray_small, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray_small, cv2.CV_32F, 0, 1, ksize=3)
        mean_abs_x = float(np.mean(np.abs(sobel_x)))
        mean_abs_y = float(np.mean(np.abs(sobel_y)))
        vertical_edge_ratio = (mean_abs_y / (mean_abs_x + 1e-4))

        # 7. Frame-to-Frame Temporal Difference
        if prev_image is not None and prev_image.shape == image.shape:
            if prev_image.ndim == 3:
                prev_gray = cv2.cvtColor(prev_image, cv2.COLOR_BGR2GRAY)
            else:
                prev_gray = prev_image
            if prev_gray.shape != gray_small.shape:
                prev_gray_small = cv2.resize(prev_gray, (gray_small.shape[1], gray_small.shape[0]), interpolation=cv2.INTER_AREA)
            else:
                prev_gray_small = prev_gray
            frame_diff = float(np.mean(cv2.absdiff(gray_small, prev_gray_small)))
        else:
            frame_diff = 0.0

        # 8. Patch Occlusion Ratio (divide into 4x4 grid and test for zero edge/texture regions)
        grid_rows, grid_cols = 4, 4
        gh, gw = gray_small.shape[0] // grid_rows, gray_small.shape[1] // grid_cols
        flat_patches = 0
        if gh > 4 and gw > 4:
            for r in range(grid_rows):
                for c in range(grid_cols):
                    patch_gray = gray_small[r * gh : (r + 1) * gh, c * gw : (c + 1) * gw]
                    patch_std = float(np.std(patch_gray))
                    patch_edge = np.count_nonzero(edges[r * gh : (r + 1) * gh, c * gw : (c + 1) * gw])
                    # If patch has near-zero variation and zero edges
                    if patch_std < 5.0 and patch_edge < 2:
                        flat_patches += 1
            patch_occlusion_ratio = float(flat_patches / (grid_rows * grid_cols))
        else:
            patch_occlusion_ratio = 0.0

        return CameraMetrics(
            brightness=round(brightness, 2),
            brightness_p5=round(float(p5), 2),
            brightness_p95=round(float(p95), 2),
            contrast=round(contrast, 2),
            laplacian_variance=round(laplacian_var, 2),
            white_pixel_ratio=round(white_ratio, 4),
            edge_density=round(edge_density, 4),
            frame_difference=round(frame_diff, 2),
            vertical_edge_ratio=round(vertical_edge_ratio, 3),
            patch_occlusion_ratio=round(patch_occlusion_ratio, 3),
        )

    @classmethod
    def classify(cls, metrics: CameraMetrics) -> DetectionResult:
        """Classify camera condition based on quantitative vision metrics."""
        # 1. Dead Feed / Whole Black
        if metrics.brightness < 12.0 and metrics.brightness_p95 < 25.0 and metrics.contrast < 10.0:
            return DetectionResult(
                condition="DEAD_FEED",
                confidence=0.95,
                reliability_score=cls.RELIABILITY_SCORES["DEAD_FEED"],
                metrics=metrics,
                reason=f"Whole black/dead feed detected: mean brightness={metrics.brightness:.1f}, contrast={metrics.contrast:.1f}",
            )

        # 2. Full White / Extreme Overexposure
        if metrics.white_pixel_ratio >= 0.75 and metrics.brightness > 235.0:
            return DetectionResult(
                condition="FULL_WHITE_OVEREXPOSURE",
                confidence=0.95,
                reliability_score=cls.RELIABILITY_SCORES["FULL_WHITE_OVEREXPOSURE"],
                metrics=metrics,
                reason=f"Full white/overexposed feed: {int(metrics.white_pixel_ratio * 100)}% saturated white pixels",
            )

        # 3. Partial White Overexposure / Severe Glare
        if 0.15 <= metrics.white_pixel_ratio < 0.75 and metrics.brightness > 160.0:
            return DetectionResult(
                condition="PARTIAL_WHITE_OVEREXPOSURE",
                confidence=0.85,
                reliability_score=cls.RELIABILITY_SCORES["PARTIAL_WHITE_OVEREXPOSURE"],
                metrics=metrics,
                reason=f"Partial glare/overexposure detected: {int(metrics.white_pixel_ratio * 100)}% saturated white pixels",
            )

        # 4. Physical Obstruction / Blocked Lens
        # Large contiguous textureless region (>40% of grid patches) while overall contrast is not dead
        if metrics.patch_occlusion_ratio >= 0.38 and metrics.edge_density < 0.012 and metrics.contrast > 10.0:
            return DetectionResult(
                condition="OBSTRUCTED",
                confidence=0.90,
                reliability_score=cls.RELIABILITY_SCORES["OBSTRUCTED"],
                metrics=metrics,
                reason=f"Lens obstructed/blocked view: {int(metrics.patch_occlusion_ratio * 100)}% field of view occluded",
            )

        # 5. Blurred / Out-of-Focus
        if metrics.laplacian_variance < 25.0 and metrics.contrast > 14.0 and metrics.edge_density < 0.009:
            return DetectionResult(
                condition="BLURRED",
                confidence=0.90,
                reliability_score=cls.RELIABILITY_SCORES["BLURRED"],
                metrics=metrics,
                reason=f"Feed blurred or out of focus: Laplacian focus={metrics.laplacian_variance:.1f} (nominal > 50.0)",
            )

        # 6. Opaque / Low Contrast
        if metrics.contrast < 13.5 and 15.0 <= metrics.brightness <= 230.0:
            return DetectionResult(
                condition="LOW_CONTRAST",
                confidence=0.85,
                reliability_score=cls.RELIABILITY_SCORES["LOW_CONTRAST"],
                metrics=metrics,
                reason=f"Opaque/low-contrast feed: contrast std={metrics.contrast:.1f} (nominal > 25.0)",
            )

        # 7. Heavy Rain (high vertical streak ratio + elevated frame jitter)
        if metrics.vertical_edge_ratio >= 1.85 and metrics.frame_difference >= 6.0 and metrics.edge_density >= 0.015:
            return DetectionResult(
                condition="HEAVY_RAIN",
                confidence=0.75,
                reliability_score=cls.RELIABILITY_SCORES["HEAVY_RAIN"],
                metrics=metrics,
                reason=f"Heavy rain streaks detected: vertical edge ratio={metrics.vertical_edge_ratio:.2f}, temporal diff={metrics.frame_difference:.1f}",
            )

        # 8. Fog / Atmospheric Haze (low edge density + low/medium contrast + elevated minimum luminance)
        if metrics.edge_density < 0.0075 and metrics.contrast < 26.0 and metrics.brightness_p5 > 35.0:
            return DetectionResult(
                condition="FOG_HAZE",
                confidence=0.80,
                reliability_score=cls.RELIABILITY_SCORES["FOG_HAZE"],
                metrics=metrics,
                reason=f"Atmospheric fog/haze detected: edge density={metrics.edge_density:.4f}, contrast={metrics.contrast:.1f}",
            )

        # 9. Clear Feed
        # Modulate score slightly around 95-100 based on Laplacian focus and contrast
        quality_factor = min(1.0, (metrics.laplacian_variance / 150.0) * 0.5 + (metrics.contrast / 60.0) * 0.5)
        score = int(95 + round(quality_factor * 5))

        return DetectionResult(
            condition="CLEAR",
            confidence=0.98,
            reliability_score=min(100, max(95, score)),
            metrics=metrics,
            reason="CCTV feed is clear and unobstructed",
        )
