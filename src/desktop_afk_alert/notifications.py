"""Independent, bounded provider deliveries. Credentials never enter error messages."""

import json
import logging
import math
import re
import socket
import ssl
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, Signal
from PySide6.QtGui import QImage

from desktop_afk_alert import __version__
from desktop_afk_alert.config import Credentials, Settings

logger = logging.getLogger(__name__)

DISCORD_ERRORS = {
    10015: "The webhook no longer exists. Create a new channel webhook.",
    40333: "Discord blocked the request. Check the network or proxy configuration.",
    50001: "The webhook cannot access the destination channel.",
    50013: "The webhook lacks permission to send to the destination channel.",
    50027: "The webhook token is invalid. Copy the complete URL from Discord.",
    50035: "Discord rejected the message or attachment format.",
    50045: "The attachment exceeds the provider's upload limit.",
    220001: "A forum or media channel requires a thread_id in the webhook URL.",
}


@dataclass(frozen=True)
class Incident:
    identifier: str
    timestamp: str
    hostname: str
    trigger: str
    message: str

    @classmethod
    def create(cls, trigger: str, message: str):
        return cls(uuid4().hex, datetime.now().astimezone().isoformat(timespec="seconds"), socket.gethostname(), trigger, message)

    @property
    def text(self) -> str:
        return f"DESKTOP AFK ALERT\nHost: {self.hostname}\nTime: {self.timestamp}\nTrigger: {self.trigger}\nIncident: {self.identifier}\n\n{self.message}"


def chunks(text: str, limit: int):
    current, length = [], 0
    for character in text:
        size = 2 if ord(character) > 0xFFFF else 1
        if length + size > limit:
            yield "".join(current)
            current, length = [], 0
        current.append(character)
        length += size
    if current:
        yield "".join(current)


class DeliveryError(Exception):
    pass


def rejection(response: httpx.Response) -> str:
    message = f"The provider rejected the alert (HTTP {response.status_code})."
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        code = None
    if type(code) is int:
        message += f" Provider code: {code}."
        if code in DISCORD_ERRORS:
            message += " " + DISCORD_ERRORS[code]
    # Provider bodies and exception strings can echo credentials or message text.
    return message


def post(client: httpx.Client, url: str, *, data=None, files=None, payload=None, context="Notification"):
    for attempt in range(3):
        try:
            response = client.post(url, data=data, files=files, json=payload)
        except (httpx.HTTPError, OSError) as error:
            reason = f"Request timed out ({type(error).__name__})." if isinstance(error, httpx.TimeoutException) else f"Connection failed ({type(error).__name__}). Check connectivity, DNS, proxy, and TLS settings."
            if attempt == 2:
                raise DeliveryError(reason + " Delivery stopped after three attempts.") from None
            logger.warning("%s: %s Retrying request (%s/3).", context, reason, attempt + 2)
            time.sleep(attempt + 1)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 2:
                raise DeliveryError(rejection(response) + " Delivery stopped after three attempts.")
            retry = attempt + 1
            try:
                body = response.json()
                retry = float(body.get("retry_after", body.get("parameters", {}).get("retry_after", response.headers.get("Retry-After", retry))))
            except (ValueError, TypeError, AttributeError):
                pass
            if not math.isfinite(retry) or retry > 10:
                raise DeliveryError("The provider requested a longer retry delay. Delivery was stopped.")
            logger.warning("%s: HTTP %s. Retrying request (%s/3) in %.1f seconds.", context, response.status_code, attempt + 2, max(0.1, retry))
            time.sleep(max(0.1, retry))
            continue
        if not 200 <= response.status_code < 300:
            raise DeliveryError(rejection(response))
        logger.info("%s: request accepted (HTTP %s).", context, response.status_code)
        return response
    raise DeliveryError("Delivery failed.")


def photo_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    image = QImage(path)
    if image.isNull():
        raise DeliveryError("The saved photo could not be read.")
    if image.width() > 1920 or image.height() > 1920:
        image = image.scaled(1920, 1920, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "JPEG", 85):
        raise DeliveryError("The photo could not be prepared for upload.")
    data = bytes(buffer.data())
    if len(data) > 8 * 1024 * 1024:
        raise DeliveryError("The photo exceeds the upload size limit.")
    return data


def discord_alert(client, webhook: str, incident: Incident, photo: bytes | None):
    url = httpx.URL(webhook.strip()).copy_set_param("wait", "true")
    context = f"Discord incident {incident.identifier}"
    for content in chunks(incident.text, 2000):
        post(client, url, payload={"content": content, "allowed_mentions": {"parse": []}}, context=context)
    if photo:
        payload = {"content": "Camera photo · " + incident.identifier, "allowed_mentions": {"parse": []}, "attachments": [{"id": 0, "filename": "camera.jpg"}]}
        post(client, url, data={"payload_json": json.dumps(payload)}, files={"files[0]": ("camera.jpg", photo, "image/jpeg")}, context=context)


def telegram_alert(client, token: str, chat_id: str, incident: Incident, photo: bytes | None):
    base = "https://api.telegram.org/bot" + token
    context = f"Telegram incident {incident.identifier}"
    for text in chunks(incident.text, 4096):
        response = post(client, base + "/sendMessage", payload={"chat_id": chat_id, "text": text}, context=context)
        if not response.json().get("ok"):
            raise DeliveryError("Telegram rejected the message.")
    if photo:
        response = post(client, base + "/sendPhoto", data={"chat_id": chat_id, "caption": "Camera photo · " + incident.identifier}, files={"photo": ("camera.jpg", photo, "image/jpeg")}, context=context)
        if not response.json().get("ok"):
            raise DeliveryError("Telegram rejected the photo.")


class Notifications(QObject):
    delivered = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tls_context = None
        self.tls_error = ""
        try:
            # Initialize OpenSSL on the GUI thread before delivery workers use it.
            self.tls_context = httpx.create_ssl_context()
        except Exception as error:
            self.tls_error = f"HTTPS initialization failed ({type(error).__name__}). Check the certificate and TLS configuration."
            logger.error(self.tls_error)

    def send(self, settings: Settings, credentials: Credentials, incident: Incident, photo_path: str | None):
        providers = []
        if settings.discord_enabled:
            providers.append("Discord")
        if settings.telegram_enabled:
            providers.append("Telegram")
        for provider in providers:
            threading.Thread(target=self._deliver, args=(provider, settings, credentials, incident, photo_path), daemon=True).start()

    def _deliver(self, provider, settings, credentials, incident, photo_path):
        note = ""
        logger.info("Sending %s alert for incident %s (photo: %s).", provider, incident.identifier, bool(photo_path))
        try:
            if self.tls_context is None:
                raise DeliveryError(self.tls_error)
            try:
                photo = photo_bytes(photo_path)
            except (DeliveryError, OSError) as error:
                photo = None
                note = " The photo was unavailable."
                logger.warning("%s incident %s: photo attachment unavailable (%s); sending text only.", provider, incident.identifier, type(error).__name__)
            timeout = httpx.Timeout(connect=5, read=10, write=10, pool=5)
            with httpx.Client(timeout=timeout, verify=self.tls_context, follow_redirects=False, headers={"User-Agent": f"desktop-afk-alert/{__version__}"}) as client:
                if provider == "Discord":
                    discord_alert(client, credentials.discord_webhook, incident, photo)
                else:
                    telegram_alert(client, credentials.telegram_token, settings.telegram_chat_id, incident, photo)
            message = "Alert delivered." + note
            logger.info("%s incident %s: %s", provider, incident.identifier, message)
        except DeliveryError as error:
            message = str(error)
            logger.error("%s incident %s: %s", provider, incident.identifier, message)
        except Exception as error:
            message = f"Could not deliver the alert ({type(error).__name__})."
            if isinstance(error, ssl.SSLError) and re.fullmatch(r"[A-Z0-9_]+", error.reason or ""):
                message += f" TLS reason: {error.reason}."
            frames = traceback.extract_tb(error.__traceback__)[-3:]
            location = " -> ".join(f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})" for frame in frames)
            logger.error("%s incident %s: %s Source: %s", provider, incident.identifier, message, location)
        try:
            self.delivered.emit(provider, message)
        except RuntimeError:
            pass
