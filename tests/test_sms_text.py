import pytest

from app.sms_text import GSM7_BASIC, GSM7_EXTENSION, to_gsm7


@pytest.mark.parametrize(
    ("turkish", "folded"),
    [
        ("Ortadoğu'daki gerilim", "Ortadogu'daki gerilim"),
        ("İstanbul", "Istanbul"),
        ("ışık", "isik"),
        ("çğıöşü", "cgiosu"),
        ("ÇĞIİÖŞÜ", "CGIIOSU"),
        ("yüzde 3,18 yükseldi", "yuzde 3,18 yukseldi"),
    ],
)
def test_to_gsm7_folds_turkish_letters(turkish: str, folded: str) -> None:
    assert to_gsm7(turkish) == folded


def test_to_gsm7_replaces_typographic_punctuation() -> None:
    """An em dash or a curly quote alone would drag the message back to UCS-2."""
    assert to_gsm7("petrol — ve “altın” … yükseldi") == 'petrol - ve "altin" ... yukseldi'


def test_to_gsm7_keeps_the_unavailable_marker_readable() -> None:
    """main.py renders a failed category with brackets, which are GSM-7 escapes."""
    assert to_gsm7("[unavailable: SummarizationError]") == "[unavailable: SummarizationError]"


def test_to_gsm7_drops_characters_it_cannot_fold() -> None:
    assert to_gsm7("kâr 📈 arttı") == "kar  artti"


def test_to_gsm7_leaves_plain_ascii_untouched() -> None:
    text = "Arsenal FC 2-1 Chelsea FC (2026-08-16)"
    assert to_gsm7(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "Konya'da meydana gelen bir trafik kazasında 2 kişi hayatını kaybetti.",
        "REMX yüzde 3,18 yükseldi; gümüş yüzde 1,54 düştü — portföy karışık.",
        "Dün Şanlıurfa'da oynanan maçta İstanbulspor 2-2 berabere kaldı…",
    ],
)
def test_to_gsm7_output_never_forces_ucs2(text: str) -> None:
    """The whole point: after folding, Twilio must not fall back to UCS-2."""
    assert all(char in GSM7_BASIC or char in GSM7_EXTENSION for char in to_gsm7(text))


def test_to_gsm7_is_idempotent() -> None:
    text = "Ortadoğu'daki gerilim petrol fiyatlarını yükseltti."
    assert to_gsm7(to_gsm7(text)) == to_gsm7(text)


def test_to_gsm7_handles_empty_input() -> None:
    assert to_gsm7("") == ""
