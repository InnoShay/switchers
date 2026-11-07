import pytest

from roomservice.contracts.config import load_desk_config
from roomservice.desk import allowlist as al


@pytest.fixture
def cfg(fixtures_dir):
    return load_desk_config(fixtures_dir / "desk_example.yaml")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://github.com/InnoShay/switchers?tab=readme#x",
        "http://localhost:5173",
        "http://localhost:3000/path",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:7777/x",
    ],
)
def test_allowed_urls(url):
    assert al.url_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://192.168.1.5:80",
        "http://localhost.evil.com:80",
        "http://localhost:80@evil.com",
        "https://user:pw@example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hi",
        "ftp://example.com",
        "https://",
        "https:///nohost",
        "example.com",
        "",
        "https://exa mple.com",
        "https://example.com\n.evil.com",
        "http://localhost:notaport",
    ],
)
def test_denied_urls(url):
    assert not al.url_allowed(url)


def test_check_url_alias_resolves(cfg):
    c = al.check_url("github", cfg)
    assert c.ok and c.value.startswith("https://github.com")


def test_check_url_raw_https(cfg):
    assert al.check_url("https://example.org/x", cfg).ok


def test_check_url_denied_has_reason(cfg):
    c = al.check_url("file:///etc/passwd", cfg)
    assert not c.ok and "not allowed" in c.reason
    assert not al.check_url("javascript:alert(1)", cfg).ok
    assert not al.check_url("http://example.com", cfg).ok


def test_check_url_unknown_alias(cfg):
    c = al.check_url("steam", cfg)
    assert not c.ok and c.reason == "not on the allowlist"


def test_check_app_ok(cfg):
    c = al.check_app("notes", cfg)
    assert c.ok and c.value == "notes"


def test_check_app_unknown_matches_a13(cfg):
    c = al.check_app("Steam", cfg)
    assert not c.ok
    assert c.reason == "not on the allowlist"
    from roomservice.desk import receipts

    assert (
        receipts.refused("open Steam", c.reason) == "⛔ refused · open Steam — not on the allowlist"
    )


def test_app_keys_are_exact_not_display_names(cfg):
    assert not al.check_app("Visual Studio Code", cfg).ok


def test_check_script(cfg):
    c, s = al.check_script("deploy", cfg)
    assert c.ok and s is not None and s.confirm is True
    c, s = al.check_script("test", cfg)
    assert c.ok and s is not None and s.confirm is False


def test_check_script_unknown(cfg):
    c, s = al.check_script("rm-rf", cfg)
    assert not c.ok and s is None and c.reason == "not on the allowlist"


def test_resolve_project_url(cfg):
    assert al.resolve_project_url("http://localhost:5173", cfg).ok
    assert al.resolve_project_url("github", cfg).value.startswith("https://github.com")
    assert not al.resolve_project_url("nope", cfg).ok
