"""Fresh clone: `up` falls back to config/desk.example.yaml when config/desk.yaml is missing."""

from pathlib import Path

import pytest
import typer

from roomservice import cli
from roomservice.contracts.config import load_settings

ROOT = Path(__file__).resolve().parents[2]


def test_falls_back_to_example_when_default_missing(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "desk.example.yaml").write_text(
        (ROOT / "config" / "desk.example.yaml").read_text()
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SWITCH_URL", "http://localhost:9")
    cfg = cli._load_cfg(load_settings())
    assert cfg.machine_name


def test_missing_custom_path_still_errors(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SWITCH_URL", "http://localhost:9")
    monkeypatch.setenv("ROOMSERVICE_DESK_CONFIG", "nope.yaml")
    with pytest.raises(typer.Exit):
        cli._load_cfg(load_settings())
