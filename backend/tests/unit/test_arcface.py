"""Unit tests for ArcFace feature extractor and cosine similarity."""
import numpy as np
import pytest
from app.vision.face.arcface import ArcFaceRecognizer, MobileFaceNetArcFace


def test_arcface_model_structure():
    model = MobileFaceNetArcFace(embedding_size=512)
    assert model.embedding_size == 512
    # Ensure parameter count is reasonable for edge deployment (< 5M params)
    param_count = sum(p.numel() for p in model.parameters())
    assert 500_000 < param_count < 5_000_000


def test_arcface_embedding_extraction():
    recognizer = ArcFaceRecognizer(device="cpu")
    # Synthetic face image 128x128
    img = np.full((128, 128, 3), 120, dtype=np.uint8)
    # Add simple facial structure variations
    img[40:60, 30:50] = [30, 30, 30]    # eye 1
    img[40:60, 78:98] = [30, 30, 30]    # eye 2
    img[85:105, 45:83] = [200, 50, 50]  # mouth

    embedding = recognizer.extract_embedding(img)
    assert embedding is not None
    assert embedding.shape == (512,)
    # Embedding must be L2 normalized (norm = 1.0)
    norm = np.linalg.norm(embedding)
    assert np.isclose(norm, 1.0, atol=1e-4)


def test_arcface_cosine_similarity():
    recognizer = ArcFaceRecognizer(device="cpu")
    img1 = np.full((120, 120, 3), 100, dtype=np.uint8)
    img1[30:50, 30:50] = 10

    emb1 = recognizer.extract_embedding(img1)
    assert emb1 is not None

    # Identical image should have similarity ~ 1.0
    sim_self = recognizer.compute_similarity(emb1, emb1)
    assert np.isclose(sim_self, 1.0, atol=1e-4)

    # Different image
    img2 = np.full((120, 120, 3), 220, dtype=np.uint8)
    img2[80:110, 80:110] = 255
    emb2 = recognizer.extract_embedding(img2)
    assert emb2 is not None

    sim_diff = recognizer.compute_similarity(emb1, emb2)
    assert sim_diff < 0.99  # Distinct images must not match identically
