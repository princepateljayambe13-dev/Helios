"""Unit tests for OSNet Re-ID architecture and OSNetExtractor."""
import numpy as np
import pytest
import torch

from app.tracking.reid.osnet import OSNet, OSNetExtractor


def test_osnet_model_structure():
    """Verify OSNet architecture dimensions, forward pass output, and unit L2 normalization."""
    model = OSNet(embedding_size=512)
    model.eval()

    dummy_input = torch.randn(2, 3, 256, 128)
    with torch.no_grad():
        output = model(dummy_input)

    assert output.shape == (2, 512), f"Expected shape (2, 512), got {output.shape}"

    # Verify unit L2 normalization: ||e||_2 == 1.0
    norms = torch.norm(output, p=2, dim=1).numpy()
    assert np.allclose(norms, 1.0, atol=1e-4), f"Embeddings must be unit L2-normalized: {norms}"


def test_osnet_extractor_synthetic_fallback():
    """Verify deterministic embedding generation when images are not supplied."""
    extractor = OSNetExtractor(device="cpu")

    emb1 = extractor.extract_embedding(image=None, synthetic_seed="person_alpha")
    emb2 = extractor.extract_embedding(image=None, synthetic_seed="person_alpha")
    emb_diff = extractor.extract_embedding(image=None, synthetic_seed="person_beta")

    assert len(emb1) == 512
    # Deterministic output for same seed
    assert emb1 == emb2
    # Distinct output for different seed
    assert emb1 != emb_diff

    # Verify unit norm
    norm = np.linalg.norm(np.array(emb1))
    assert norm == pytest.approx(1.0, abs=1e-3)


def test_osnet_extractor_image_preprocessing_and_extraction():
    """Verify crop preprocessing, margin framing, and feature extraction on numpy image."""
    extractor = OSNetExtractor(device="cpu")

    # Create dummy 1080x1920 image
    image = np.full((1080, 1920, 3), 120, dtype=np.uint8)
    # Add distinct color pattern in person box
    image[200:600, 300:500] = [30, 180, 75]

    bbox = [300 / 1920.0, 200 / 1080.0, 200 / 1920.0, 400 / 1080.0]
    tensor = extractor.preprocess_crop(image, bbox)

    assert tensor is not None
    assert tensor.shape == (1, 3, 256, 128)

    emb = extractor.extract_embedding(image=image, bounding_box=bbox)
    assert len(emb) == 512
    norm = np.linalg.norm(np.array(emb))
    assert norm == pytest.approx(1.0, abs=1e-3)


def test_osnet_cosine_similarity():
    """Verify cosine similarity mathematical boundaries."""
    e1 = [1.0, 0.0, 0.0]
    e2 = [1.0, 0.0, 0.0]
    e_ortho = [0.0, 1.0, 0.0]
    e_opp = [-1.0, 0.0, 0.0]

    assert OSNetExtractor.cosine_similarity(e1, e2) == pytest.approx(1.0)
    assert OSNetExtractor.cosine_similarity(e1, e_ortho) == pytest.approx(0.0)
    assert OSNetExtractor.cosine_similarity(e1, e_opp) == pytest.approx(-1.0)
