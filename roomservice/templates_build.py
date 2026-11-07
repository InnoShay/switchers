"""Build Switch templates: inline instruction files into the template YAML (SPEC §10.2)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

MARKER = re.compile(r"^@@FILE:([^@]+\.md)@@$")


class TemplateBuildError(Exception):
    pass


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_representer)


def _expand(node: Any, instructions_dir: Path) -> Any:
    if isinstance(node, str):
        m = MARKER.match(node)
        if not m:
            return node
        path = instructions_dir / m.group(1)
        if not path.is_file():
            raise TemplateBuildError(f"missing instruction file: {path}")
        return path.read_text(encoding="utf-8")
    if isinstance(node, dict):
        return {k: _expand(v, instructions_dir) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand(v, instructions_dir) for v in node]
    return node


def _dump(data: Any) -> str:
    return yaml.dump(
        data,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=10_000,
        default_flow_style=False,
    )


def build_template(src: Path, instructions_dir: Path, dist_dir: Path) -> Path:
    """Build one template; returns the written path."""
    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    out = _dump(_expand(data, instructions_dir))
    if "@@FILE:" in out:
        raise TemplateBuildError(f"{src.name}: unresolved @@FILE: marker remains")
    dist_dir.mkdir(parents=True, exist_ok=True)
    dest = dist_dir / src.name
    dest.write_text(out, encoding="utf-8")
    return dest


def build_all(switch_dir: Path | None = None) -> list[Path]:
    """Build every switch/templates/*.template.yaml into switch/templates/dist/."""
    base = switch_dir or Path(__file__).resolve().parent.parent / "switch"
    sources = sorted((base / "templates").glob("*.template.yaml"))
    if not sources:
        raise TemplateBuildError(f"no templates found in {base / 'templates'}")
    return [build_template(s, base / "instructions", base / "templates" / "dist") for s in sources]


def run_build_templates() -> None:
    """CLI body for `roomservice build-templates`."""
    import typer
    from rich.console import Console

    console = Console()
    try:
        for p in build_all():
            console.print(f"built {p}")
    except TemplateBuildError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
