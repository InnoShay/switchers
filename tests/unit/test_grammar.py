import pytest

from roomservice.desk.grammar import (
    Command,
    ParseError,
    command_lines,
    parse_command,
    parse_message,
    too_many_commands_text,
)


def cmd(text: str) -> Command:
    out = parse_command(text)
    assert isinstance(out, Command), out
    return out


# -- each verb ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "verb", "args"),
    [
        ("boot volt", "boot", ["volt"]),
        ("mission volt-waitlist volt", "mission", ["volt-waitlist", "volt"]),
        ("mission scratch none", "mission", ["scratch", "none"]),
        ("open notes", "open", ["notes"]),
        ("url github", "url", ["github"]),
        ("url https://example.com/a?b=1", "url", ["https://example.com/a?b=1"]),
        ("run test", "run", ["test"]),
        ("focus on", "focus", ["on"]),
        ("focus off", "focus", ["off"]),
        ("shot", "shot", []),
        ("shot screen", "shot", ["screen"]),
        ("shot page", "shot", ["page"]),
        ('say "hello there"', "say", ["hello there"]),
        ("close music", "close", ["music"]),
        ("close all", "close", ["all"]),
        ('commit "waitlist page v1"', "commit", ["waitlist page v1"]),
        ("push", "push", []),
        ("wrap", "wrap", []),
        ("resume volt", "resume", ["volt"]),
        ("status", "status", []),
        ("lights on", "lights", ["on"]),
        ("release", "release", []),
        ("pair 123456", "pair", ["123456"]),
        ("ok K7Q3", "ok", ["K7Q3"]),
        ("no K7Q3", "no", ["K7Q3"]),
        ("freeze", "freeze", []),
        ("unfreeze", "unfreeze", []),
        ("help", "help", []),
    ],
)
def test_each_verb(text, verb, args):
    c = cmd(text)
    assert (c.verb, c.args, c.raw) == (verb, args, text)


# -- aliases --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "verb"),
    [
        ("screenshot", "shot"),
        ("show", "shot"),
        ("snap", "shot"),
        ("show-me", "shot"),
        ("speak hi", "say"),
        ("start volt", "boot"),
        ("goodnight", "wrap"),
        ("stop", "freeze"),
        ("halt", "freeze"),
        ("approve K7Q3", "ok"),
        ("yes K7Q3", "ok"),
        ("deny K7Q3", "no"),
        ("reject K7Q3", "no"),
    ],
)
def test_aliases(text, verb):
    assert cmd(text).verb == verb


def test_verb_is_case_insensitive_but_args_keep_case():
    c = cmd("OPEN Notes")
    assert (c.verb, c.args) == ("open", ["Notes"])


def test_show_me_drops_the_me():
    c = cmd("show me")
    assert (c.verb, c.args) == ("shot", [])


def test_show_me_page_keeps_argument():
    assert cmd("show me page").args == ["page"]


# -- quotes and escapes ---------------------------------------------------------------


def test_single_quotes():
    assert cmd("say 'good evening sir'").args == ["good evening sir"]


def test_escaped_quote_inside_double_quotes():
    assert cmd(r'say "she said \"hi\""').args == ['she said "hi"']


def test_backslash_escaped_space():
    assert cmd(r"say hello\ world").args == ["hello world"]


def test_multiple_args_and_extra_spaces():
    assert cmd("  mission   a    b  ").args == ["a", "b"]


def test_unbalanced_double_quote_is_parse_error():
    out = parse_command('say "oops')
    assert isinstance(out, ParseError)
    assert out.raw == 'say "oops'
    assert "unbalanced" in out.reason


def test_unbalanced_single_quote_is_parse_error():
    assert isinstance(parse_command("say 'oops"), ParseError)


def test_trailing_backslash_is_parse_error():
    assert isinstance(parse_command("say oops\\"), ParseError)


def test_empty_and_blank_command():
    assert isinstance(parse_command(""), ParseError)
    assert isinstance(parse_command("   "), ParseError)


def test_unknown_verb():
    out = parse_command("dance now")
    assert isinstance(out, ParseError)
    assert "dance" in out.reason


# -- mention lines --------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "@hands boot volt",
        "@hands, boot volt",
        "@hands: boot volt",
        "@HANDS: boot volt",
        "@Hands boot volt",
        "@desk-laptop boot volt",
        "@desk-laptop, boot volt",
        "@desk-backup: boot volt",
        "   @hands boot volt   ",
    ],
)
def test_mention_variants(body):
    r = parse_message(body)
    assert r.commands == [Command("boot", ["volt"], "boot volt")]
    assert r.refusal is None


def test_unaddressed_without_mention_yields_nothing():
    r = parse_message("hello team, lunch?", addressed=False)
    assert r.items == []


def test_other_mention_is_not_a_command_line():
    assert parse_message("@builder boot volt", addressed=False).items == []


def test_mention_without_command_is_not_a_line():
    assert command_lines("@hands", addressed=False) == []


def test_multi_line_each_line_is_a_command():
    r = parse_message("@hands boot volt\n@hands open notes\n@hands shot")
    assert [c.verb for c in r.commands] == ["boot", "open", "shot"]


def test_multi_line_ignores_chatter_between_commands():
    r = parse_message("hey\n@hands status\nthanks!\n@hands, help")
    assert [c.verb for c in r.commands] == ["status", "help"]


def test_crlf_lines():
    r = parse_message("@hands status\r\n@hands help\r\n")
    assert [c.verb for c in r.commands] == ["status", "help"]


# -- addressed fallback ---------------------------------------------------------------


def test_addressed_fallback_whole_body():
    r = parse_message("show me", addressed=True)
    assert r.commands == [Command("shot", [], "show me")]


def test_addressed_fallback_strips_all_at_tokens():
    r = parse_message("please @hands open @desk-laptop notes", addressed=True)
    assert r.items == [ParseError("please open notes", "unknown verb 'please'")]
    r = parse_message("@concierge status", addressed=True)
    assert r.commands == [Command("status", [], "status")]


def test_addressed_fallback_not_used_when_a_line_matches():
    r = parse_message("blah blah\n@hands status", addressed=True)
    assert [c.verb for c in r.commands] == ["status"]
    assert len(r.items) == 1


def test_addressed_unknown_text_is_parse_error():
    r = parse_message("make the button orange", addressed=True)
    assert len(r.items) == 1
    assert isinstance(r.items[0], ParseError)


def test_addressed_empty_body():
    r = parse_message("", addressed=True)
    assert len(r.items) == 1 and isinstance(r.items[0], ParseError)


def test_addressed_only_mentions():
    r = parse_message("@hands", addressed=True)
    assert len(r.items) == 1 and isinstance(r.items[0], ParseError)


def test_empty_unaddressed():
    r = parse_message("", addressed=False)
    assert r.items == [] and r.refusal is None


def test_unbalanced_quotes_in_mention_line():
    r = parse_message('@hands say "oops')
    assert len(r.items) == 1 and isinstance(r.items[0], ParseError)


# -- limit of 5 commands --------------------------------------------------------------


def test_five_commands_ok():
    body = "\n".join("@hands status" for _ in range(5))
    r = parse_message(body)
    assert len(r.commands) == 5
    assert r.refusal is None


def test_more_than_five_commands_refused_text_exact():
    body = "\n".join(f"@hands open app{i}" for i in range(7))
    r = parse_message(body)
    assert len(r.items) == 5
    assert r.refusal == "⛔ refused · more than 5 commands in one message"
    assert [c.args[0] for c in r.commands] == [f"app{i}" for i in range(5)]


def test_max_commands_is_configurable():
    r = parse_message("@hands status\n@hands help", max_commands=1)
    assert len(r.items) == 1
    assert (
        r.refusal == too_many_commands_text(1) == "⛔ refused · more than 1 commands in one message"
    )
