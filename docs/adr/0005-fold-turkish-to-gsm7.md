# 5. Strip Turkish Diacritics From the SMS Body

## Status
Accepted

## Context
The brief is delivered in Turkish. Twilio picks an SMS encoding from the message body, and one character outside the GSM-7 alphabet is enough to force UCS-2 for the whole message. Turkish guarantees that fallback: `ı`, `İ`, `ğ`, `Ğ`, `ş`, `Ş` and lowercase `ç` are all absent from GSM-7. (`ö`, `ü` and `Ç` happen to be present and cost nothing.)

The difference is not marginal. A concatenated UCS-2 segment carries 67 characters where a GSM-7 one carries 153, and Twilio bills per segment. Measured against the real feeds, four Turkish categories at a 600-character cap came to 28 segments a day — roughly 840 a month.

## Decision
`src/app/sms_text.to_gsm7()` folds the message body into the GSM-7 alphabet immediately before sending: Unicode NFD decomposition strips the diacritics, dotless `ı` and the typographic punctuation an LLM tends to emit (em dash, curly quotes, ellipsis) are mapped by hand, and anything still outside the alphabet is dropped.

The fold applies to the SMS body only. `main.py`'s terminal output keeps proper Turkish.

Alongside it, `MAX_SUMMARY_CHARS` drops from 600 to 400, which is the largest round number that keeps a folded category inside 3 segments (3 × 153 = 459) with room left for the category tag.

## Consequences
Cost falls to about 11 segments a day, roughly 330 a month — a ~60% cut, of which the fold contributes more than the shorter cap does.

The reader gets "Ortadogu'daki gerilim" instead of "Ortadoğu'daki gerilim". Turkish is readable this way and the habit predates smartphones, but it is a genuine loss and was accepted deliberately rather than by omission.

`to_gsm7` must stay exhaustive. It is a silent optimization: a single unfolded character does not raise or warn, it just doubles the bill. A test asserts that the folded output contains nothing outside GSM-7.
