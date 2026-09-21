"""Private export package and user-requested email delivery for the
historical email proof (plan sections 2-3, 9.5).

Password-protected export is explicitly deferred by the plan ("salattu
vienti lisätään erillisenä vaiheena") -- this module only builds the plain
stampd-proof.json package and sends it, on request, to the message's own
already-checked recipient address.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

PACKAGE_FORMAT = "stampd-proof-package-v1"
PACKAGE_FILENAME = "stampd-proof.json"

# (to_addr, subject, body_text, attachment_bytes, attachment_filename) -> None
SendFn = Callable[[str, str, str, bytes, str], None]


class DeliveryError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def build_proof_package(credential_jws: str, disclosure_secret_b64: str, arweave_tx_id: str) -> dict:
    return {
        "format": PACKAGE_FORMAT,
        "arweaveTxId": arweave_tx_id,
        "signedCredential": credential_jws,
        "disclosure": {"randomSecret": disclosure_secret_b64},
    }


def package_bytes(package: dict) -> bytes:
    return json.dumps(package, indent=2, sort_keys=True).encode("utf-8")


def send_proof_email(
    package: dict,
    verified_recipient_email: str,
    requested_recipient_email: str,
    send_fn: SendFn,
    arweave_gateway_url: str,
) -> None:
    """Plan section 2, point 29: the user explicitly requests delivery, but the
    send target is always the checked message's own recipient address -- never
    a freely entered third-party address, so `requested_recipient_email` (what
    the caller's UI/API received) must match `verified_recipient_email` (what
    check_message_fields/issue_credential actually verified).

    A failed send must not invalidate the already-downloadable package; this
    function only raises DeliveryError, it never deletes or revokes anything.

    Per-account send-rate limiting (plan: "Lähetysrajoitukset estävät
    toiminnon käyttämisen roskapostiin") is deliberately not implemented here
    -- it needs the app's session/store state and belongs in the endpoint
    that calls this function, not in this pure library.
    """
    if requested_recipient_email != verified_recipient_email:
        raise DeliveryError(
            "delivery must target the checked message's own recipient address, "
            "not a freely entered address"
        )

    body = (
        "Liitteenä on Stampd-todistuspakettisi (stampd-proof.json).\n\n"
        f"Julkinen Arweave-tietue: {arweave_gateway_url}\n\n"
        "Säilytä liite -- sitä tarvitaan todistuksen tuomiseen palveluihin, "
        "jotka tukevat sitä. Jos hukkaat sen, ja et myöskään lataa sitä nyt "
        "uudelleen, salaista satunnaisarvoa ei voi palauttaa Arweavesta.\n"
    )

    try:
        send_fn(verified_recipient_email, "Stampd-todistuksesi", body, package_bytes(package), PACKAGE_FILENAME)
    except Exception as exc:
        raise DeliveryError(f"email delivery failed: {exc}") from exc
