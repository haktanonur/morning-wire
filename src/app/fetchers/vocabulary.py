"""Pick the day's English vocabulary out of the owner's own notebook.

Unlike the other four categories this one neither fetches nor summarizes. The
entries are already written, in Turkish, by the person who is going to read
them, so there is nothing for the model to add and plenty it could get wrong: a
paraphrased meaning or a "corrected" example would quietly replace study
material with the model's guess at it. The words therefore travel from the file
to the SMS untouched, and this category costs no API call.

Which entries go out is a pure function of the date. Nothing is stored between
runs — the scheduled job runs on a fresh runner every morning, so any cursor
would have to be committed back into the repository or cached, and neither is
worth it for a notebook meant to be read round and round. Advancing the offset
by ``WORDS_PER_DAY`` a day walks the whole file before repeating, because 15 and
449 share no common factor, and then starts again. For vocabulary that second
pass is revision rather than a defect.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_VOCABULARY_PATH = Path(__file__).resolve().parents[3] / "data" / "vocabulary.txt"

# The real list is personal and gitignored, so it is absent from a fresh
# checkout. This one is tracked, and is the only in-repo record of the format
# the parser expects.
EXAMPLE_VOCABULARY_PATH = Path(__file__).resolve().parents[3] / "data" / "vocabulary.example.txt"

WORDS_PER_DAY = 15

# Fifteen entries render to roughly 2,300 characters, which is about 3,300 once
# percent-encoded into the trigger URL's query string. The SMS itself does not
# care — the messages come off the owner's own SIM (docs/adr/0006) — but the URL
# does: the relay is a third party with an unpublished request-line limit, and
# the failure mode if it has one is the worst kind, because it answers "200 ok"
# whether or not the whole parameter survived. Five entries a message keeps each
# URL near 1,100 characters, far inside anything plausible, and reads better on
# a phone than one eighteen-segment wall of text.
WORDS_PER_MESSAGE = 5

# The field labels used by the notebook, which is written and maintained by hand.
_TURKISH_LABEL = "Türkçe"
_NOTE_LABEL = "Not"
_EXAMPLE_LABEL = "Örnek"


class VocabularyError(RuntimeError):
    """Raised when the vocabulary file is missing or yields no usable entries."""


@dataclass(frozen=True)
class VocabularyEntry:
    """One entry from the notebook.

    Attributes:
        term: The English word or phrase, e.g. ``"set aside"``.
        turkish: Its Turkish meaning.
        note: The owner's own note on usage.
        example: An English sentence using the term.
    """

    term: str
    turkish: str
    note: str
    example: str


def _field(line: str, label: str) -> str | None:
    """Return the value of ``label`` on an indented ``  Label : value`` line.

    ``None`` if the line is not that field, which is how the parser recognises
    an entry: chapter headings, rules and blank lines all fail this test, so
    nothing has to know what they look like.
    """
    if not line.startswith(" "):
        return None
    name, separator, value = line.partition(":")
    if not separator or name.strip() != label:
        return None
    return value.strip()


def parse_entries(text: str) -> tuple[VocabularyEntry, ...]:
    """Read every entry out of the notebook's text.

    An entry is a term on its own line followed by its three indented fields in
    order. Anything else — the file header, the chapter headings, the ``===``
    rules — simply fails to match and is skipped, so the parser needs no
    knowledge of them.

    Args:
        text: The whole file.

    Returns:
        Every well-formed entry, in file order. A malformed one is logged and
        skipped rather than raising: the notebook is hand-maintained and still
        growing, and one bad entry should not cost the reader the other 448.
    """
    lines = text.splitlines()
    entries: list[VocabularyEntry] = []

    index = 0
    while index < len(lines) - 1:
        term = lines[index].strip()
        turkish = _field(lines[index + 1], _TURKISH_LABEL)
        if not term or turkish is None:
            index += 1
            continue

        note = _field(lines[index + 2], _NOTE_LABEL) if index + 2 < len(lines) else None
        example = _field(lines[index + 3], _EXAMPLE_LABEL) if index + 3 < len(lines) else None
        if note is None or example is None:
            logger.warning("Vocabulary entry %r is missing a note or an example; skipping.", term)
            index += 2
            continue

        entries.append(VocabularyEntry(term=term, turkish=turkish, note=note, example=example))
        index += 4

    return tuple(entries)


def load_vocabulary(path: Path | None = None) -> tuple[VocabularyEntry, ...]:
    """Read the notebook from disk.

    Args:
        path: File to read. Defaults to ``data/vocabulary.txt``.

    Returns:
        Every entry in the file, in file order.

    Raises:
        VocabularyError: If the file cannot be read, or parses to nothing. An
            empty result means the format changed, which is worth failing on:
            silently sending no words would look exactly like a quiet day.
    """
    source = path if path is not None else DEFAULT_VOCABULARY_PATH

    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise VocabularyError(f"Vocabulary file not found at {source}.") from exc

    entries = parse_entries(text)
    if not entries:
        raise VocabularyError(f"Vocabulary file at {source} has no usable entries.")
    return entries


def select_for_day(
    entries: tuple[VocabularyEntry, ...],
    day: date,
    count: int = WORDS_PER_DAY,
) -> tuple[VocabularyEntry, ...]:
    """Take the ``count`` entries belonging to ``day``.

    The offset is derived from the date alone, so the same day always yields the
    same words however often it runs — a re-run after a failure repeats the
    morning's list rather than skipping ahead past it.

    Args:
        entries: The whole notebook.
        day: The day to select for.
        count: How many entries to take.

    Returns:
        ``count`` entries, wrapping back to the start of the notebook at the end
        so that no day is short.
    """
    start = (day.toordinal() * count) % len(entries)
    return tuple(entries[(start + offset) % len(entries)] for offset in range(count))


def render_entry(number: int, entry: VocabularyEntry) -> str:
    """Format one entry for the SMS.

    The markers are ``=``, ``*`` and ``>`` rather than words because all three
    are in the GSM-7 basic alphabet and cost one unit each, and because a label
    like "Türkçe" would be folded to "Turkce" on the way out anyway.
    """
    return f"{number}. {entry.term}\n= {entry.turkish}\n* {entry.note}\n> {entry.example}"


def daily_messages(
    day: date | None = None,
    path: Path | None = None,
) -> tuple[str, ...]:
    """Build the day's vocabulary as one rendered body per message.

    Args:
        day: The day to select for. Defaults to today.
        path: Notebook to read. Defaults to ``data/vocabulary.txt``.

    Returns:
        ``WORDS_PER_DAY / WORDS_PER_MESSAGE`` bodies, each holding
        ``WORDS_PER_MESSAGE`` entries numbered continuously across the whole
        day, so the reader can see that all fifteen arrived.

    Raises:
        VocabularyError: If the notebook is missing or unreadable.
    """
    chosen = select_for_day(load_vocabulary(path), day if day is not None else date.today())
    return tuple(
        "\n\n".join(
            render_entry(start + offset + 1, entry)
            for offset, entry in enumerate(chosen[start : start + WORDS_PER_MESSAGE])
        )
        for start in range(0, len(chosen), WORDS_PER_MESSAGE)
    )
