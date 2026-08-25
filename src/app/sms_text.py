"""Fold Turkish text into the GSM-7 alphabet so an SMS costs half as many segments.

Whatever sends the message picks the encoding from the body: one character
outside GSM-7 is enough to force UCS-2 for the *whole* message, and a
concatenated UCS-2 segment carries 67 characters where a GSM-7 one carries 153.
Turkish guarantees that fallback — ``ı``, ``İ``, ``ğ``, ``Ğ``, ``ş``, ``Ş`` and
lowercase ``ç`` are all missing from GSM-7 — so an untouched Turkish brief takes
roughly twice the segments it needs to.

Dropping the diacritics ("Ortadogu" for "Ortadoğu") is a readability trade the
owner accepted to halve that. Since the move to MacroDroid the segments come out
of the owner's own mobile plan rather than a Twilio bill, so the fold now buys
fewer messages on the phone and an ASCII-only body that survives a URL query
parameter intact, rather than a smaller invoice — see ``docs/adr/0005`` and
``docs/adr/0006``.

Only the SMS body is folded; ``main.py``'s terminal output keeps proper Turkish.
"""

from __future__ import annotations

import unicodedata

# The GSM 03.38 basic alphabet. Every character here costs one unit.
GSM7_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# The extension table. Still GSM-7, but each character costs two units because
# it is sent as an escape pair. ``[`` and ``]`` matter here: main.py renders a
# failed category as "[unavailable: ...]".
GSM7_EXTENSION = frozenset("^{}\\[~]|€")

# NFD decomposition turns ç, ğ, ö, ş, ü and the accented Latin letters into a
# base letter plus a combining mark, so stripping the marks is enough for them.
# Dotless ı has no decomposition, and the typographic punctuation an LLM likes
# to emit has none either, so both are mapped by hand — an em dash left in place
# would silently drag the whole message back to UCS-2.
_REPLACEMENTS = {
    "ı": "i",
    "—": "-",
    "–": "-",
    "‑": "-",
    "“": '"',
    "”": '"',
    "„": '"',
    "‘": "'",
    "’": "'",
    "…": "...",
    "\u00a0": " ",
    "\u2009": " ",
}


def to_gsm7(text: str) -> str:
    """Rewrite ``text`` so that every character is in the GSM-7 alphabet.

    Args:
        text: Turkish (or any) prose, as produced by ``summarizer.py``.

    Returns:
        The same text with diacritics stripped and typographic punctuation
        replaced by ASCII. Anything still outside GSM-7 after that is dropped
        rather than replaced with a placeholder, so a stray symbol costs a
        character instead of littering the message with ``?``.
    """
    replaced = "".join(_REPLACEMENTS.get(char, char) for char in text)
    unmarked = "".join(
        char for char in unicodedata.normalize("NFD", replaced) if not unicodedata.combining(char)
    )
    return "".join(char for char in unmarked if char in GSM7_BASIC or char in GSM7_EXTENSION)
