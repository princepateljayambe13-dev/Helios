import pytest
from app.core.config import Settings, load_settings

def test_load_settings_defaults():
    settings = load_settings()
    assert isinstance(settings, Settings)
    assert settings.api_prefix == "/api/v1"
    assert len(settings.cameras) > 0
