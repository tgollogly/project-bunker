from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class SmsProvider(Protocol):
    def send(self, message: str) -> None: ...


class StubSmsProvider:
    def __init__(self) -> None:
        self.last_message: str | None = None

    def send(self, message: str) -> None:
        self.last_message = message
        logger.info("Stub SMS: %s", message[:80])


class TwilioSmsProvider:
    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_number: str,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        self._from = from_number
        self._to = to_number

    def send(self, message: str) -> None:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._sid}/Messages.json"
        with httpx.Client(timeout=30.0, auth=(self._sid, self._token)) as client:
            resp = client.post(
                url,
                data={"From": self._from, "To": self._to, "Body": message[:320]},
            )
            resp.raise_for_status()
        logger.info("Twilio SMS sent to %s", self._to)


def build_sms_provider(provider: str) -> SmsProvider:
    if provider == "twilio":
        sid = os.environ.get("BUNKER_TWILIO_ACCOUNT_SID", "")
        token = os.environ.get("BUNKER_TWILIO_AUTH_TOKEN", "")
        from_n = os.environ.get("BUNKER_TWILIO_FROM", "")
        to_n = os.environ.get("BUNKER_SMS_TO", "")
        if not all([sid, token, from_n, to_n]):
            raise RuntimeError("Twilio env vars missing")
        return TwilioSmsProvider(
            account_sid=sid, auth_token=token, from_number=from_n, to_number=to_n
        )
    return StubSmsProvider()