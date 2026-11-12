import pytest


@pytest.fixture(autouse=True)
def no_range_cache(monkeypatch):
    """Tests never read or write the user's cache of downloaded ranges."""
    monkeypatch.setenv("N_ANTIBOT_CACHE", "off")
