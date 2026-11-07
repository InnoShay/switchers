from pathlib import Path

import pytest

from roomservice.contracts.config import ConfigError, Settings, load_desk_config


def test_example_desk_config_loads(fixtures_dir):
    cfg = load_desk_config(fixtures_dir / "desk_example.yaml")
    assert cfg.machine_name == "laptop"
    assert cfg.projects["volt"].terminals[0].name == "dev"
    assert cfg.scripts["deploy"].confirm is True
    assert cfg.limits.approval_ttl_s == 300


def test_tilde_is_expanded(fixtures_dir):
    cfg = load_desk_config(fixtures_dir / "desk_example.yaml")
    path = cfg.projects["volt"].path
    assert "~" not in str(path)
    assert path == Path.home() / "roomservice-workspace/projects/volt"


def test_unknown_key_names_the_yaml_path(fixtures_dir, tmp_path):
    bad = tmp_path / "desk.yaml"
    bad.write_text((fixtures_dir / "desk_example.yaml").read_text() + "\nbogus_key: 1\n")
    with pytest.raises(ConfigError, match=r"^bogus_key: "):
        load_desk_config(bad)


def test_nested_error_names_the_full_path(fixtures_dir, tmp_path):
    text = (fixtures_dir / "desk_example.yaml").read_text().replace("rate: 190", "rate: fast")
    bad = tmp_path / "desk.yaml"
    bad.write_text(text)
    with pytest.raises(ConfigError, match=r"^voice\.rate: "):
        load_desk_config(bad)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_desk_config(tmp_path / "nope.yaml")


def test_settings_defaults_and_csv_rooms(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no stray .env
    monkeypatch.setenv("SWITCH_URL", "http://localhost:8123")
    monkeypatch.setenv("ROOMSERVICE_HQ_ROOMS", "alpha, RoomService HQ ,beta")
    monkeypatch.setenv("LIGHTS_ON_URL", "")
    s = Settings()
    assert s.roomservice_hq_rooms == ["alpha", "RoomService HQ", "beta"]
    assert s.lights_on_url is None
    assert s.hud_port == 7777
    assert s.roomservice_agent == "desk-laptop"
    assert s.n8n_life_token.get_secret_value() == "change-me"


def test_settings_requires_switch_url(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SWITCH_URL", raising=False)
    with pytest.raises(ValueError):
        Settings()


def test_env_example_parses(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    for line in (root / ".env.example").read_text().splitlines():
        if "=" in line:
            key, _, rest = line.partition("=")
            monkeypatch.setenv(key, rest.split("  #")[0].strip())
    monkeypatch.setenv("SWITCH_URL", "http://localhost:9999")
    s = Settings()
    assert s.roomservice_hq_rooms == ["roomservice-hq", "RoomService HQ"]
    assert s.switch_registration_key is None
