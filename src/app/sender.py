"""Deliver the briefing as one tagged SMS per category, via a MacroDroid webhook.

Twilio was the original Phase 2 transport but is unusable here: its Turkey
guidelines prohibit person-to-person traffic and require a registered
alphanumeric sender id. Instead the brief is pushed to the owner's own Android
phone, which sends the SMS from its own SIM. See
``docs/adr/0006-macrodroid-over-twilio.md``.

Each category goes out as its own request, so a category that fails to reach the
relay costs only itself (``PLAN.md`` §7, ``docs/adr/0004-per-category-sms.md``).
``main.py`` supplies the send order: markets → portfolio → news → sports.

**A successful call does not mean the SMS was sent.** The endpoint is a cloud
relay that pushes to the phone; it answers ``200 ok`` as soon as it has queued
the push, and it answers the same way when the phone is offline, out of credit,
or has had its SMS permission revoked. Nothing on this side can observe the
device, so :class:`SendOutcome` reports *accepted*, not *delivered*.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote

import requests

from app.config import load_macrodroid_settings
from app.sms_text import to_gsm7

logger = logging.getLogger(__name__)

# The query parameter carrying the message body. MacroDroid matches query
# parameters to variables by name, case-sensitively, and it will not create a
# variable that does not already exist: if the macro has no global string
# variable called exactly this, the macro still runs but sends an empty body and
# the relay still answers 200. Renaming this constant means renaming the
# variable on the phone.
MESSAGE_PARAM = "message"

# What the relay returns when it has accepted the trigger.
RELAY_OK_BODY = "ok"

REQUEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class SendOutcome:
    """The result of handing one category to the relay.

    Attributes:
        heading: Category name, e.g. ``"MARKETS"``.
        error: ``None`` if the relay accepted the trigger, otherwise a short
            description of why it did not.
    """

    heading: str
    error: str | None = None

    @property
    def accepted(self) -> bool:
        """Whether the relay accepted the trigger.

        Deliberately not called ``delivered``: the phone may still fail to send
        the SMS, and that failure is invisible from here.
        """
        return self.error is None


def build_message(heading: str, body: str) -> str:
    """Tag a section with its category and fold it into the GSM-7 alphabet.

    Args:
        heading: Category name, e.g. ``"MARKETS"``.
        body: The summary text, in Turkish.

    Returns:
        The SMS body, e.g. ``"[MARKETS] Piyasalar ..."``, containing nothing
        outside GSM-7.
    """
    return to_gsm7(f"[{heading}] {body}")


def build_url(trigger_url: str, message: str) -> str:
    """Append the message to the trigger URL as a percent-encoded query parameter.

    The URL is assembled by hand rather than through ``requests``' ``params=``,
    which encodes a space as ``+``. MacroDroid documents ``%20`` and says
    nothing about ``+``, so every reserved character is escaped with
    ``safe=""`` and no assumption is made about what the phone decodes.

    Args:
        trigger_url: The webhook URL, without a query string.
        message: The SMS body.

    Returns:
        The full URL to request.
    """
    return f"{trigger_url}?{MESSAGE_PARAM}={quote(message, safe='')}"


def _trigger(trigger_url: str, heading: str, body: str) -> SendOutcome:
    """Fire the webhook for a single category, converting any failure into an outcome."""
    try:
        response = requests.get(
            build_url(trigger_url, build_message(heading, body)),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        # Only the exception type: requests quotes the failing URL in its
        # message, and that URL is the credential.
        reason = type(exc).__name__
        logger.warning("SMS trigger for %s failed (%s).", heading, reason)
        return SendOutcome(heading=heading, error=reason)

    # The status is the contract; the body is a weaker signal, so an unexpected
    # one is worth surfacing but not worth failing a send that the relay took.
    if response.text.strip().lower() != RELAY_OK_BODY:
        logger.warning("SMS trigger for %s returned an unexpected body.", heading)
    return SendOutcome(heading=heading)


def send_report(sections: Iterable[tuple[str, str]]) -> tuple[SendOutcome, ...]:
    """Push every section to the phone as its own SMS, isolating failures per category.

    Args:
        sections: ``(heading, body)`` pairs in send order.

    Returns:
        One :class:`SendOutcome` per section, in the same order. An outcome that
        is ``accepted`` means the relay queued the push, not that the SMS
        arrived — see the module docstring.

    Raises:
        MissingEnvVarError: If ``MACRODROID_TRIGGER_URL`` is not configured.
            That is not a per-category failure — without it nothing can be sent
            — so it is left to the caller rather than swallowed here.
    """
    trigger_url = load_macrodroid_settings().trigger_url
    return tuple(_trigger(trigger_url, heading, body) for heading, body in sections)
