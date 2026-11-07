import json
import os
import stat

from roomservice import store


def test_atomic_write_and_read(tmp_path):
    p = tmp_path / "a" / "b.json"
    store.write_json(p, {"x": 1})
    assert store.read_json(p) == {"x": 1}
    assert [f.name for f in p.parent.iterdir()] == ["b.json"]  # no temp leftovers


def test_secret_files_are_chmod_600(tmp_path):
    p = tmp_path / "s.json"
    store.write_json(p, {"k": "v"}, secret=True)
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_corrupt_or_missing_returns_default(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert store.read_json(p, default={"d": 1}) == {"d": 1}
    assert store.read_json(tmp_path / "missing.json") is None


def test_failed_write_keeps_old_content(tmp_path):
    p = tmp_path / "keep.json"
    store.write_json(p, {"ok": True})
    try:
        store.write_json(p, {"bad": object()})
    except TypeError:
        pass
    assert json.loads(p.read_text()) == {"ok": True}
    assert [f.name for f in tmp_path.iterdir() if f.is_file()] == ["keep.json"]


def test_agent_creds_round_trip_and_mode(rs_home):
    assert store.load_agent_creds("http://x:1/", "desk-laptop") is None
    store.save_agent_creds("http://x:1/", "desk-laptop", "id1", "key1")
    store.save_agent_creds("http://x:1", "life", "id2", "key2")
    assert store.load_agent_creds("http://x:1", "desk-laptop") == {"id": "id1", "api_key": "key1"}
    assert store.load_agent_creds("http://x:1", "life")["id"] == "id2"
    assert stat.S_IMODE(os.stat(store.agents_path()).st_mode) == 0o600


def test_home_honours_env(rs_home):
    assert store.home() == rs_home
