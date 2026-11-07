from pathlib import Path

import pytest
import yaml

from roomservice.templates_build import TemplateBuildError, build_all, build_template

TEXT = "line one\n\nline two\n  indented\nlast\n"


def _setup(tmp_path: Path, body: str = TEXT, marker: str = "@@FILE:a.md@@"):
    ins = tmp_path / "ins"
    ins.mkdir()
    (ins / "a.md").write_text(body, encoding="utf-8")
    src = tmp_path / "x.template.yaml"
    src.write_text(f'version: 1\nroom:\n  instructions: "{marker}"\n  name: n\n', encoding="utf-8")
    return src, ins, tmp_path / "dist"


def test_round_trip_preserves_newlines_and_literal_block(tmp_path):
    src, ins, dist = _setup(tmp_path)
    out = build_template(src, ins, dist)
    text = out.read_text(encoding="utf-8")
    assert "instructions: |" in text
    assert yaml.safe_load(text)["room"]["instructions"] == TEXT
    assert list(yaml.safe_load(text)["room"]) == ["instructions", "name"]


def test_unicode_kept(tmp_path):
    src, ins, dist = _setup(tmp_path, body="🛎️ MISSION · done\nnext\n")
    text = build_template(src, ins, dist).read_text(encoding="utf-8")
    assert "🛎️ MISSION · done" in text


def test_missing_file_fails(tmp_path):
    src, ins, dist = _setup(tmp_path, marker="@@FILE:nope.md@@")
    with pytest.raises(TemplateBuildError, match="nope.md"):
        build_template(src, ins, dist)


def test_leftover_marker_fails(tmp_path):
    src, ins, dist = _setup(tmp_path, body="see @@FILE:other.md@@ inside\n")
    with pytest.raises(TemplateBuildError, match="@@FILE:"):
        build_template(src, ins, dist)


def test_idempotent(tmp_path):
    src, ins, dist = _setup(tmp_path)
    first = build_template(src, ins, dist).read_text(encoding="utf-8")
    second = build_template(src, ins, dist).read_text(encoding="utf-8")
    assert first == second


def test_real_templates_build(tmp_path):
    base = Path(__file__).resolve().parents[2] / "switch"
    ins = base / "instructions"
    for src in sorted((base / "templates").glob("*.template.yaml")):
        text = build_template(src, ins, tmp_path).read_text(encoding="utf-8")
        assert "@@FILE:" not in text
        assert yaml.safe_load(text)["version"] == 1
    assert len(list(tmp_path.glob("*.yaml"))) == 2
    crew = yaml.safe_load((tmp_path / "roomservice-crew.template.yaml").read_text())
    assert crew["agents"][0]["instructions"] == (ins / "concierge.md").read_text(encoding="utf-8")


def test_committed_dist_is_current():
    base = Path(__file__).resolve().parents[2] / "switch"
    for p in build_all(base):
        assert "@@FILE:" not in p.read_text(encoding="utf-8")
