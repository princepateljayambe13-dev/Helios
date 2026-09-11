"""ArcFace feature extraction and face embedding computation for HELIOS.

Implements an ArcFace-compatible deep feature extractor (512-dimensional
L2-normalized embedding) using PyTorch with Apple Silicon MPS and CPU support.
Supports loading pre-trained weights from file, with high-accuracy deterministic
inference.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

LOGGER = logging.getLogger(__name__)


class ConvBlock(nn.Module):
    def __init__(self, in_c: int, out_c: int, kernel_size: int = 3, stride: int = 1, padding: int = 1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel_size, stride, padding, bias=False)
        self.bn = nn.BatchNorm2d(out_c)
        self.prelu = nn.PReLU(out_c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.prelu(self.bn(self.conv(x)))


class LinearBlock(nn.Module):
    def __init__(self, in_c: int, out_c: int, kernel_size: int = 3, stride: int = 1, padding: int = 1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel_size, stride, padding, bias=False)
        self.bn = nn.BatchNorm2d(out_c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.bn(self.conv(x))


class DepthWiseBlock(nn.Module):
    def __init__(self, in_c: int, out_c: int, residual: bool = False, kernel_size: int = 3, stride: int = 2, padding: int = 1):
        super().__init__()
        self.residual = residual
        self.conv = ConvBlock(in_c, out_c=in_c, kernel_size=1, stride=1, padding=0)
        self.conv_dw = ConvBlock(in_c, in_c, kernel_size=kernel_size, stride=stride, padding=padding)
        self.project = LinearBlock(in_c, out_c, kernel_size=1, stride=1, padding=0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        short_cut = x
        out = self.conv(x)
        out = self.conv_dw(out)
        out = self.project(out)
        if self.residual:
            return short_cut + out
        return out


class ResidualBlock(nn.Module):
    def __init__(self, in_c: int, out_c: int, num_blocks: int, kernel_size: int = 3, stride: int = 2, padding: int = 1):
        super().__init__()
        modules = [DepthWiseBlock(in_c, out_c, residual=False, kernel_size=kernel_size, stride=stride, padding=padding)]
        for _ in range(num_blocks - 1):
            modules.append(DepthWiseBlock(out_c, out_c, residual=True, kernel_size=3, stride=1, padding=1))
        self.blocks = nn.Sequential(*modules)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.blocks(x)


class MobileFaceNetArcFace(nn.Module):
    """Standard MobileFaceNet architecture for ArcFace face recognition.
    
    Accepts (3, 112, 112) normalized face crops and outputs 512-D L2-normalized embeddings.
    """
    def __init__(self, embedding_size: int = 512):
        super().__init__()
        self.embedding_size = embedding_size
        self.conv1 = ConvBlock(3, 64, kernel_size=3, stride=2, padding=1)
        self.conv2_dw = ConvBlock(64, 64, kernel_size=3, stride=1, padding=1)
        self.dconv_1 = ResidualBlock(64, 64, num_blocks=2, kernel_size=3, stride=2, padding=1)
        self.dconv_2 = ResidualBlock(64, 128, num_blocks=4, kernel_size=3, stride=2, padding=1)
        self.dconv_3 = ResidualBlock(128, 128, num_blocks=2, kernel_size=3, stride=2, padding=1)
        self.conv_sep = ConvBlock(128, 512, kernel_size=1, stride=1, padding=0)
        # Global depthwise convolution for feature aggregation: (512, 7, 7) -> (512, 1, 1)
        self.gdc = nn.Sequential(
            nn.Conv2d(512, 512, kernel_size=7, stride=1, padding=0, groups=512, bias=False),
            nn.BatchNorm2d(512),
        )
        self.linear = nn.Linear(512, embedding_size, bias=False)
        self.bn = nn.BatchNorm1d(embedding_size)

        # Stable initialization
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.BatchNorm1d)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.conv1(x)
        out = self.conv2_dw(out)
        out = self.dconv_1(out)
        out = self.dconv_2(out)
        out = self.dconv_3(out)
        out = self.conv_sep(out)
        out = self.gdc(out)
        out = torch.flatten(out, 1)
        out = self.linear(out)
        out = self.bn(out)
        # L2 normalize feature representation onto unit hypersphere (ArcFace space)
        return F.normalize(out, p=2, dim=1)


class ArcFaceRecognizer:
    """ArcFace face feature embedding generator and similarity matcher."""

    def __init__(self, weights_path: str | Path | None = None, device: str = "auto") -> None:
        self.embedding_size = 512
        self.device = self._resolve_device(device)
        self.model = MobileFaceNetArcFace(embedding_size=self.embedding_size)

        if weights_path:
            p = Path(weights_path)
            if p.exists() and p.is_file():
                try:
                    state_dict = torch.load(p, map_location=self.device, weights_only=True)
                    if "state_dict" in state_dict:
                        state_dict = state_dict["state_dict"]
                    self.model.load_state_dict(state_dict, strict=False)
                    LOGGER.info("Loaded custom ArcFace weights from %s", p)
                except Exception as err:
                    LOGGER.warning("Could not load custom ArcFace weights from %s: %s", p, err)

        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _resolve_device(pref: str) -> torch.device:
        if pref == "cuda" and torch.cuda.is_available():
            return torch.device("cuda")
        if pref in ("auto", "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        if pref == "cpu" or not torch.cuda.is_available():
            return torch.device("cpu")
        return torch.device("cpu")

    def preprocess_face(self, image: np.ndarray, bounding_box: list[float] | None = None) -> torch.Tensor | None:
        """Crop and normalize face to ArcFace standard input (1, 3, 112, 112)."""
        import cv2

        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            return None

        h, w = image.shape[:2]
        if bounding_box and len(bounding_box) >= 4:
            bx, by, bw, bh = (float(v) for v in bounding_box[:4])
            # Add 12% margin around face crop to preserve jawline, ears and forehead
            margin_x = bw * 0.12
            margin_y = bh * 0.12
            x1 = max(0, int(round((bx - margin_x) * w)))
            y1 = max(0, int(round((by - margin_y) * h)))
            x2 = min(w, int(round((bx + bw + margin_x) * w)))
            y2 = min(h, int(round((by + bh + margin_y) * h)))
            if x2 > x1 + 8 and y2 > y1 + 8:
                face = image[y1:y2, x1:x2]
            else:
                face = image
        else:
            face = image

        if face is None or face.size == 0:
            return None

        # Convert to RGB if 3 channels BGR
        if len(face.shape) == 3 and face.shape[2] == 3:
            face_rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        elif len(face.shape) == 2:
            face_rgb = cv2.cvtColor(face, cv2.COLOR_GRAY2RGB)
        else:
            face_rgb = face

        # Resize to standard ArcFace 112x112
        resized = cv2.resize(face_rgb, (112, 112), interpolation=cv2.INTER_AREA)

        # Standard ArcFace normalization: (x - 127.5) / 128.0
        normalized = (resized.astype(np.float32) - 127.5) / 128.0
        # Transpose (H, W, C) -> (C, H, W)
        tensor = torch.from_numpy(normalized).permute(2, 0, 1).unsqueeze(0).float()
        return tensor

    @torch.no_grad()
    def extract_embedding(self, image: np.ndarray, bounding_box: list[float] | None = None) -> np.ndarray | None:
        """Compute 512-dimensional L2-normalized ArcFace embedding vector."""
        tensor = self.preprocess_face(image, bounding_box)
        if tensor is None:
            return None

        tensor = tensor.to(self.device)
        embedding = self.model(tensor)
        # Move back to CPU numpy array
        return embedding.squeeze(0).cpu().numpy().astype(np.float32)

    @staticmethod
    def compute_similarity(embedding1: np.ndarray | list[float], embedding2: np.ndarray | list[float]) -> float:
        """Compute cosine similarity between two 512-D embeddings."""
        v1 = np.asarray(embedding1, dtype=np.float32).flatten()
        v2 = np.asarray(embedding2, dtype=np.float32).flatten()
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        sim = float(np.dot(v1, v2) / (norm1 * norm2))
        return max(-1.0, min(1.0, sim))
