"""Tests for the vocabulary category.

Two things are being protected here. One is the parser, which reads a file
written by hand and will keep being appended to. The other is the *selection*:
it has no stored state, so its only guarantee that the reader eventually sees
every word is arithmetic, and arithmetic is worth asserting.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest

from app.fetchers.vocabulary import (
    EXAMPLE_VOCABULARY_PATH,
    WORDS_PER_DAY,
    WORDS_PER_MESSAGE,
    VocabularyEntry,
    VocabularyError,
    daily_messages,
    load_vocabulary,
    parse_entries,
    render_entry,
    select_for_day,
)
from app.sms_text import to_gsm7

NOTEBOOK = """EXPLAINED — KELİME VE KALIP DEFTERİ
Toplam bölüm: 1 | Toplam kelime: 2

======================================================================
Bölüm 1 — Racial Wealth Gap (13 Temmuz 2026)
======================================================================

picking cotton
  Türkçe : pamuk toplamak
  Not    : Özellikle tarım işçiliği bağlamında kullanılır.
  Örnek  : Enslaved people spent long days picking cotton.

set aside
  Türkçe : bir kenara ayırmak
  Not    : Para veya zaman ayırmak için de kullanılır.
  Örnek  : The government set aside land for returning soldiers.
"""


def _entries(count: int) -> tuple[VocabularyEntry, ...]:
    """A notebook of ``count`` entries, each one identifiable by its index."""
    return tuple(
        VocabularyEntry(term=f"term{n}", turkish=f"tr{n}", note=f"note{n}", example=f"ex{n}")
        for n in range(count)
    )


# --- parsing ----------------------------------------------------------------


def test_parse_reads_every_field_and_ignores_the_scaffolding() -> None:
    """The file header, the chapter heading and the === rules are not entries."""
    assert parse_entries(NOTEBOOK) == (
        VocabularyEntry(
            term="picking cotton",
            turkish="pamuk toplamak",
            note="Özellikle tarım işçiliği bağlamında kullanılır.",
            example="Enslaved people spent long days picking cotton.",
        ),
        VocabularyEntry(
            term="set aside",
            turkish="bir kenara ayırmak",
            note="Para veya zaman ayırmak için de kullanılır.",
            example="The government set aside land for returning soldiers.",
        ),
    )


def test_parse_keeps_a_value_that_contains_a_colon() -> None:
    """Notes quote English, and English quotes use colons."""
    (entry,) = parse_entries(
        "break down\n"
        "  Türkçe : parçalamak\n"
        '  Not    : Kullanım: "Let\'s break it down."\n'
        "  Örnek  : Let's break down the numbers.\n"
    )

    assert entry.note == 'Kullanım: "Let\'s break it down."'


def test_parse_skips_a_malformed_entry_but_keeps_the_rest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One bad hand-written entry must not cost the reader the whole notebook."""
    broken = NOTEBOOK + "\nhalf an entry\n  Türkçe : yarım kayıt\n"

    with caplog.at_level(logging.WARNING):
        entries = parse_entries(broken)

    assert [entry.term for entry in entries] == ["picking cotton", "set aside"]
    assert "half an entry" in caplog.text


def test_load_raises_when_the_notebook_is_missing(tmp_path: Path) -> None:
    with pytest.raises(VocabularyError, match="not found"):
        load_vocabulary(tmp_path / "absent.txt")


def test_load_raises_when_nothing_parses(tmp_path: Path) -> None:
    """An empty result means the format moved; sending no words would look like a quiet day."""
    path = tmp_path / "vocabulary.txt"
    path.write_text("just some prose\nand another line\n", encoding="utf-8")

    with pytest.raises(VocabularyError, match="no usable entries"):
        load_vocabulary(path)


# --- the committed example --------------------------------------------------


def test_the_example_notebook_parses_completely() -> None:
    """Guards `data/vocabulary.example.txt`, the only in-repo record of the format.

    The real list is personal, gitignored and restored from a secret on the
    runner, so it cannot be asserted against here — which leaves the example
    file carrying the format on its own. If the parser changes and the example
    is not updated with it, every new deployment starts from a file that no
    longer works, and nothing else would catch that.
    """
    entries = load_vocabulary(EXAMPLE_VOCABULARY_PATH)

    assert entries
    assert all(entry.term and entry.turkish and entry.note and entry.example for entry in entries)


# --- selection --------------------------------------------------------------


def test_the_same_day_always_gives_the_same_words() -> None:
    """A re-run after a failed send repeats the morning's list, it does not skip it."""
    notebook = _entries(449)

    first = select_for_day(notebook, date(2026, 9, 7))
    second = select_for_day(notebook, date(2026, 9, 7))

    assert first == second
    assert len(first) == WORDS_PER_DAY


def test_consecutive_days_do_not_overlap() -> None:
    notebook = _entries(449)

    today = select_for_day(notebook, date(2026, 9, 7))
    tomorrow = select_for_day(notebook, date(2026, 9, 8))

    assert set(today).isdisjoint(tomorrow)


def test_the_wrap_at_the_end_still_gives_a_full_day() -> None:
    """449 is not a multiple of 15, so one day a month straddles the end."""
    notebook = _entries(20)

    chosen = select_for_day(notebook, date(2026, 9, 7), count=WORDS_PER_DAY)

    assert len(chosen) == WORDS_PER_DAY
    assert len(set(chosen)) == WORDS_PER_DAY, "a short notebook must not repeat within one day"


def test_a_month_of_runs_covers_the_whole_notebook() -> None:
    """The only guarantee that no word is stranded: 15 and 449 share no factor."""
    notebook = _entries(449)
    start = date(2026, 9, 7)

    seen = {
        entry
        for offset in range(30)
        for entry in select_for_day(notebook, start + timedelta(days=offset))
    }

    assert seen == set(notebook)


# --- rendering --------------------------------------------------------------


def test_render_marks_the_three_fields() -> None:
    entry = VocabularyEntry("set aside", "kenara ayırmak", "Para için de.", "They set aside land.")

    assert render_entry(4, entry) == (
        "4. set aside\n= kenara ayırmak\n* Para için de.\n> They set aside land."
    )


def test_the_markers_survive_the_gsm7_fold() -> None:
    """``=``, ``*`` and ``>`` are basic-alphabet characters, so the fold leaves them alone."""
    rendered = render_entry(1, _entries(1)[0])

    assert to_gsm7(rendered) == rendered


def test_a_day_splits_into_whole_messages_numbered_continuously() -> None:
    messages = daily_messages(date(2026, 9, 7), path=EXAMPLE_VOCABULARY_PATH)

    assert len(messages) == WORDS_PER_DAY // WORDS_PER_MESSAGE
    assert messages[0].startswith("1. ")
    assert messages[1].startswith(f"{WORDS_PER_MESSAGE + 1}. ")
    assert all(body.count("\n= ") == WORDS_PER_MESSAGE for body in messages)


def test_every_message_stays_well_inside_a_url() -> None:
    """The reason the day is split at all: the body travels as a query parameter.

    The relay answers ``200 ok`` whether or not an overlong parameter survived,
    so there is no way to notice this going wrong from the outside.

    Measured against the example notebook, whose entries are written at the same
    length as the real one — the real list is gitignored and not on a runner
    until the secret is expanded, so it cannot be the thing under test.
    """
    for body in daily_messages(date(2026, 9, 7), path=EXAMPLE_VOCABULARY_PATH):
        encoded = quote(to_gsm7(f"[VOCAB 1/3] {body}"), safe="")

        assert len(encoded) < 2000


def test_daily_messages_surfaces_a_missing_notebook(tmp_path: Path) -> None:
    with pytest.raises(VocabularyError):
        daily_messages(date(2026, 9, 7), path=tmp_path / "absent.txt")
