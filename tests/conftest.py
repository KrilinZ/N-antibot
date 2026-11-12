import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never touch the network or the user's cache unless they say so."""
    monkeypatch.setenv("N_ANTIBOT_CACHE", "off")
    monkeypatch.setattr("n_antibot.ai.protected_ranges", lambda download=None: ({}, []))
