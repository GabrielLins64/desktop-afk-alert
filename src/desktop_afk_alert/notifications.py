"""Independent, bounded provider deliveries. Credentials never enter error messages."""

import json
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, Signal
from PySide6.QtGui import QImage

from desktop_afk_alert.config import Credentials, Settings


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


def post(client: httpx.Client, url: str, *, data=None, files=None, payload=None):
    for attempt in range(3):
        try:
            response = client.post(url, data=data, files=files, json=payload)
        except (httpx.HTTPError, OSError):
            if attempt == 2:
                raise DeliveryError("Connection failed or timed out.") from None
            time.sleep(attempt + 1)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 2:
                raise DeliveryError(f"The provider returned HTTP {response.status_code}.")
            retry = attempt + 1
            try:
                body = response.json()
                retry = float(body.get("retry_after", body.get("parameters", {}).get("retry_after", retry)))
            except (ValueError, TypeError, AttributeError):
                pass
            if retry > 10:
                raise DeliveryError("The provider requested a longer retry delay. Delivery was stopped.")
            time.sleep(max(0.1, retry))
            continue
        if not 200 <= response.status_code < 300:
            raise DeliveryError(f"The provider rejected the alert (HTTP {response.status_code}).")
        return response
    raise DeliveryError("Delivery failed.")


def photo_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    image = QImage(path)
    if image.isNull():
        raise DeliveryError("The saved photo could not be read.")
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
    separator = "&" if "?" in webhook else "?"
    url = webhook + separator + "wait=true"
    for content in chunks(incident.text, 2000):
        post(client, url, payload={"content": content, "allowed_mentions": {"parse": []}})
    if photo:
        payload = {"content": "Camera photo · " + incident.identifier, "allowed_mentions": {"parse": []}, "attachments": [{"id": 0, "filename": "camera.jpg"}]}
        post(client, url, data={"payload_json": json.dumps(payload)}, files={"files[0]": ("camera.jpg", photo, "image/jpeg")})


def telegram_alert(client, token: str, chat_id: str, incident: Incident, photo: bytes | None):
    base = "https://api.telegram.org/bot" + token
    for text in chunks(incident.text, 4096):
        response = post(client, base + "/sendMessage", payload={"chat_id": chat_id, "text": text})
        if not response.json().get("ok"):
            raise DeliveryError("Telegram rejected the message.")
    if photo:
        response = post(client, base + "/sendPhoto", data={"chat_id": chat_id, "caption": "Camera photo · " + incident.identifier}, files={"photo": ("camera.jpg", photo, "image/jpeg")})
        if not response.json().get("ok"):
            raise DeliveryError("Telegram rejected the photo.")


class Notifications(QObject):
    delivered = Signal(str, str)

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
        try:
            try:
                photo = photo_bytes(photo_path)
            except (DeliveryError, OSError):
                photo = None
                note = " The photo was unavailable."
            timeout = httpx.Timeout(connect=3, read=5, write=5, pool=3)
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                if provider == "Discord":
                    discord_alert(client, credentials.discord_webhook, incident, photo)
                else:
                    telegram_alert(client, credentials.telegram_token, settings.telegram_chat_id, incident, photo)
            message = "Alert delivered." + note
        except DeliveryError as error:
            message = str(error)
        except Exception:
            message = "Could not deliver the alert."
        try:
            self.delivered.emit(provider, message)
        except RuntimeError:
            pass
