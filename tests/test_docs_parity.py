"""Five hand-written translations of the same rules drift silently.

`RULES.fr.md` kept claiming that a sealed mission card discloses its severity for a
full release after the other four were corrected, because the only thing checking
them was a human reading five files. Backticked identifiers are the part of these
documents that is NOT translated, so English is the canonical list and every
translation must carry the same technical vocabulary.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
LANGUAGES = ("ru", "es", "fr", "zh")
STEMS = ("RULES", "GUIDE")

_LITERAL = re.compile(r"`([^`\n]{1,64})`")

# Literals a translation may legitimately omit, per stem, with the reason. Every entry
# is asserted to still exist in the English source, so a stale exemption fails loudly
# instead of quietly widening the hole it was opened for.
ALLOWED_OMISSIONS: dict[str, dict[str, str]] = {
    "RULES": {
        "K=4": "inline math shorthand, spelled out in prose per language",
        "latency_ms = null": "spelled as a sentence in zh rather than a code span",
    },
    "GUIDE": {},
}


def _literals(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    found = set()
    for token in _LITERAL.findall(text):
        # Placeholders are localized on purpose: `https://<signal-hunt-domain>` becomes
        # `https://<домен-signal-hunt>`. Non-ASCII spans are typeset math (`oᵢ`, `pᵢ`).
        if "<" in token or ">" in token or not token.isascii():
            continue
        found.add(token)
    return found


def _path(stem: str, lang: str | None) -> Path:
    return DOCS_DIR / (f"{stem}.md" if lang is None else f"{stem}.{lang}.md")


def test_every_language_of_every_document_exists():
    for stem in STEMS:
        for lang in (None, *LANGUAGES):
            assert _path(stem, lang).is_file(), (stem, lang)


def test_technical_vocabulary_is_identical_across_translations():
    for stem in STEMS:
        english = _literals(_path(stem, None))
        exempt = set(ALLOWED_OMISSIONS[stem])
        for token in exempt:
            assert token in english, (
                f"{stem}: exemption `{token}` is no longer in the English source — "
                "remove it from ALLOWED_OMISSIONS"
            )
        for lang in LANGUAGES:
            missing = english - _literals(_path(stem, lang)) - exempt
            assert not missing, f"{stem}.{lang}.md is missing {sorted(missing)}"


def test_no_ruleset_leaks_the_sealed_severity():
    """Severity is part of the answer: `calm` meant `stable` and killed the 4-way choice.

    The retired claim read the same in all five files, so the string itself is the
    tripwire — a translation that reintroduces it fails here.
    """
    for lang in (None, *LANGUAGES):
        text = _path("RULES", lang).read_text(encoding="utf-8")
        assert "`anomaly` / `calm`" not in text, lang
        for band in ("`low`", "`elevated`", "`high`"):
            assert band in text, (lang, band)
