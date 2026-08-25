# 6. Send the SMS From the Owner's Own Phone via MacroDroid, Not Twilio

## Status
Accepted. Supersedes the Twilio transport assumed by ADR 0003 and ADR 0004.

## Context
Phase 2 was planned around Twilio from the start. Checking Twilio's own Turkey guidelines before implementing it turned up three blockers, not one:

- **Person-to-person traffic is prohibited.** Twilio's Turkey rules cover application-to-person messaging. A daily briefing sent to its own author is exactly the P2P case they exclude.
- **A registered alphanumeric sender id is mandatory** — long codes are not supported for Turkey — and registration wants corporate documents and takes weeks. From 18 November 2026 unregistered sender ids are blocked outright, so a trial-account send that works today is not a path to production.
- **It costs money per segment**, which is what drove ADR 0005.

NetGSM was evaluated as the local alternative. It has no P2P ban and is cheap (~90 TL/month), but sender-name registration is still mandatory, it requires a KEP address and an e-Devlet residence document, and its docs do not confirm that an individual rather than a company can register at all.

Both routes ask a single-user personal project to present itself as a business.

## Decision
The brief is delivered by the owner's own Android phone. `sender.py` makes one HTTP GET per category to a MacroDroid webhook (`https://trigger.macrodroid.com/<device-id>/<trigger-name>`), passing the message as a `message` query parameter; a macro on the phone reads it and fires a Send SMS action from the phone's own SIM.

The phone-side contract, which is not visible from this repo and is easy to get wrong:

- The macro must own a **global string variable named exactly `message`** (case-sensitive). MacroDroid matches query parameters to variables by name and **will not create one that does not exist** — a name mismatch does not error, it sends an empty body.
- The macro references it as `{v=message}`, not `{message}`.
- The **recipient number lives in the macro**, not here. That keeps a real phone number out of the repo, which `AGENTS.md` requires anyway.
- The trigger URL is the credential: anyone holding it can fire the macro. It lives in `.env` as `MACRODROID_TRIGGER_URL` and is regenerable from the app.

## Consequences
No sender-id registration, no corporate paperwork, no per-segment bill, no regulatory deadline. The SMS is a normal person-to-person message from a Turkish SIM to a Turkish number, so it arrives the way any text does. No new Python dependency either — it is one `requests` call, where Twilio needed an SDK.

**Delivery is no longer observable.** The endpoint is a cloud relay: it answers `200 ok` once it has queued a push, and answers exactly the same way when the phone is switched off, out of credit, or has had its SMS permission revoked. `SendOutcome` therefore reports `accepted`, deliberately not `delivered`. Phase 3's failure logging cannot cover the last hop, and a silent non-delivery is a real failure mode this design accepts.

The phone becomes infrastructure. If it is off or offline at 06:00 the brief is lost, and there is no retry. That is tolerable for a personal briefing in a way it would not be for anything with an audience.

Availability now depends on a third-party relay and on MacroDroid remaining installed and licensed, in exchange for not depending on Twilio's account standing.

ADR 0005's fold survives the move but its justification changes: the saving is no longer a bill, since the messages come out of the owner's own mobile plan. It stays because Turkish characters would push the phone into UCS-2 (70 characters a segment) and because a folded, ASCII-only body passes through a URL query parameter with nothing left to misencode. Reverting to full Turkish is now an affordable option rather than an expensive one, and is worth revisiting if the transliteration grates.
