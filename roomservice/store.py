"""~/.roomservice persistence: atomic JSON writes, chmod 600 for secrets."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def home() -> Path:
    """Runtime home dir. ROOMSERVICE_HOME overrides the default ~/.roomservice."""
    return Path(os.environ.get("ROOMSERVICE_HOME", "~/.roomservice")).expanduser()


def ensure_dir(path: Path, mode: int = 0o700) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    return path


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON; missing or corrupt file returns `default`."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any, secret: bool = False) -> None:
    """Atomically write JSON (temp file + rename). `secret=True` sets mode 600."""
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600 if secret else 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- well-known files -------------------------------------------------------------------


def agents_path() -> Path:
    return home() / "agents.json"


def cursors_path() -> Path:
    return home() / "cursors.json"


def owners_path() -> Path:
    return home() / "owners.json"


def state_dir() -> Path:
    return ensure_dir(home() / "state")


def shots_dir() -> Path:
    return ensure_dir(home() / "shots")


def logs_dir() -> Path:
    return ensure_dir(home() / "logs")


def load_agent_creds(switch_url: str, name: str) -> dict[str, str] | None:
    """agents.json shape: {"<switch_url>": {"<name>": {"id": ..., "api_key": ...}}}."""
    data = read_json(agents_path(), {})
    return data.get(switch_url.rstrip("/"), {}).get(name)


def save_agent_creds(switch_url: str, name: str, agent_id: str, api_key: str) -> None:
    data = read_json(agents_path(), {})
    data.setdefault(switch_url.rstrip("/"), {})[name] = {"id": agent_id, "api_key": api_key}
    write_json(agents_path(), data, secret=True)
