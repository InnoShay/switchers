"""Frozen contract (SPEC §8.1): .env settings and desk.yaml models."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    HttpUrl,
    SecretStr,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ConfigError(Exception):
    """Raised for invalid desk.yaml. Message format: '<yaml.path>: <msg>'."""


class Settings(BaseSettings):  # from .env (pydantic-settings)
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    switch_url: AnyHttpUrl
    switch_registration_key: SecretStr | None = None
    roomservice_agent: Literal["desk-laptop", "desk-backup"] = "desk-laptop"
    # names or room UUIDs, comma-separated in .env
    roomservice_hq_rooms: Annotated[list[str], NoDecode] = ["roomservice-hq", "RoomService HQ"]
    roomservice_tz: str = "Asia/Kolkata"
    roomservice_home: Path = Path("~/.roomservice").expanduser()
    roomservice_desk_config: Path = Path("config/desk.yaml")
    roomservice_dry_run: bool = False
    roomservice_handoff_mode: Literal["lease", "explicit"] = "lease"  # S8 picks default
    roomservice_relay_approvals: bool = True  # S5 picks default
    hud_port: int = 7777
    n8n_life_url: AnyHttpUrl = "http://localhost:5678/webhook/roomservice-life"
    n8n_life_token: SecretStr = SecretStr("change-me")
    lights_on_url: str | None = None
    lights_off_url: str | None = None

    @field_validator("roomservice_hq_rooms", mode="before")
    @classmethod
    def _split_rooms(cls, v: object) -> object:
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return v

    @field_validator("roomservice_home", mode="after")
    @classmethod
    def _expand_home(cls, v: Path) -> Path:
        return v.expanduser()


class AppTarget(BaseModel):
    mac: str
    win: str
    linux: str


class ScriptDef(BaseModel):
    cmd: list[str]
    cwd: Literal["project", "home"] = "project"
    confirm: bool = False
    timeout_s: int = 120


class Terminal(BaseModel):
    name: str
    cmd: str


class Project(BaseModel):
    keywords: list[str]
    path: Path
    open_editor: bool = True
    terminals: list[Terminal] = []
    urls: list[str] = []  # each url: alias key or http(s) URL
    wait_for: str | None = None
    screenshot_url: str | None = None
    focus: bool = True
    music: str | None = None
    lights: bool = True


class Profile(BaseModel):
    apps: list[str] = []
    urls: list[str] = []
    focus: bool = True
    lights: bool = True
    music: str | None = None


class Voice(BaseModel):
    enabled: bool = True
    voice_name: str = "Samantha"
    rate: int = 190


class Ignition(BaseModel):
    wake_phrases: list[str]
    default_profile: str


class Schedule(BaseModel):
    morning_brief: str = "08:55"
    morning_days: str = "mon-sat"
    wrap_nudge: str = "23:00"


class Limits(BaseModel):
    actions_per_minute: int = 20
    max_commands_per_message: int = 5
    approval_ttl_s: int = 300


class DeskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    machine_name: str
    timezone: str
    voice: Voice
    ignition: Ignition
    apps: dict[str, AppTarget]
    urls: dict[str, HttpUrl]
    scripts: dict[str, ScriptDef]
    projects: dict[str, Project]
    profiles: dict[str, Profile]
    schedule: Schedule = Schedule()
    limits: Limits = Limits()


def load_settings() -> Settings:
    """Load Settings from the environment and ./.env."""
    return Settings()  # type: ignore[call-arg]


def load_desk_config(path: Path) -> DeskConfig:
    """Load and validate desk.yaml. Expands ~. Raises ConfigError('<yaml.path>: <msg>')."""
    path = Path(path).expanduser()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"{path}: cannot read file ({e.strerror or e})") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML ({e})") from e
    if not isinstance(raw, dict):
        raise ConfigError("<root>: desk.yaml must be a mapping")
    try:
        cfg = DeskConfig.model_validate(raw)
    except ValidationError as e:
        err = e.errors()[0]
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        raise ConfigError(f"{loc}: {err['msg']}") from e
    for project in cfg.projects.values():
        project.path = project.path.expanduser()
    return cfg
