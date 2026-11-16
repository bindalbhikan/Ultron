"""docs/CENTRALISE.md step 3: the bots' Telegram text helpers come from the agent's module, unchanged."""
from ultron.workings.core import telegram as bots

SAMPLES = [
    "plain & <simple>",
    "**Sale** today\n- MAIN: 12\n* DBCC: `3`\n# Heading\n| a | b |\n|---|---|\n| 1 | 2 |",
    "<b>" + "x" * 5000 + "</b>",
    "<pre>" + "\n".join(f"line {i} &amp; more" for i in range(900)) + "</pre>",
    "a" * 9000,
]
# what the bots' split_html gave before the move (16 Nov 2026): part counts and a fingerprint of every part
EXPECTED_PARTS = [1, 1, 2, 5, 3]
EXPECTED_SHA1 = "7cd15ae112b9c10cffc37af0855debcbae810117"


def test_split_html_gives_exactly_what_it_gave_before():
    import hashlib
    assert hashlib.sha1(repr([bots.split_html(s) for s in SAMPLES]).encode()).hexdigest() == EXPECTED_SHA1


def test_esc_md_plain_the_same():
    from ultron.integrations import telegram as agent
    for s in SAMPLES:
        assert bots.esc(s) == agent.esc(s)
        assert bots.md(s) == agent.md(s)
        assert bots._plain(s) == agent._plain(s)


def test_split_html_keeps_tags_whole_and_parts_short():
    for s, n in zip(SAMPLES, EXPECTED_PARTS):
        parts = bots.split_html(s)
        assert len(parts) == n
        assert all(len(p) <= bots.MAX_LEN for p in parts)
        assert "".join(parts).count("<b>") >= s.count("<b>")
        for p in parts:                                   # every part closes what it opens
            for tag in ("b", "pre"):
                assert p.count(f"<{tag}>") == p.count(f"</{tag}>")
