"""Shared fixtures. Tests never touch the real ~/.roomservice or a real Switch."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def rs_home(tmp_path, monkeypatch):
    """Point ROOMSERVICE_HOME at a temp dir for every test."""
    home = tmp_path / "rs-home"
    monkeypatch.setenv("ROOMSERVICE_HOME", str(home))
    return home


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def fresh_bus():
    from roomservice.bus import Bus

    return Bus()
