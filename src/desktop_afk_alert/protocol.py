"""Small, bounded protocol shared by the GUI and privileged helper."""

import json
from enum import StrEnum

PROTOCOL_VERSION = 2
MAX_MESSAGE_BYTES = 32768
HEARTBEAT_TIMEOUT = 5.0


class State(StrEnum):
    IDLE = "IDLE"
    COUNTDOWN = "COUNTDOWN"
    ARMED = "ARMED"
    FROZEN = "FROZEN"
    AUTHENTICATING = "AUTHENTICATING"


def encode(message_type: str, **values: object) -> bytes:
    payload = {"version": PROTOCOL_VERSION, "type": message_type, **values}
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Protocol message is too large.")
    return data + b"\n"


def decode(data: bytes) -> dict:
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("Protocol message is too large.")
    message = json.loads(data)
    if not isinstance(message, dict) or message.get("version") != PROTOCOL_VERSION:
        raise ValueError("Incompatible helper protocol. Reinstall the helper.")
    if not isinstance(message.get("type"), str):
        raise ValueError("Invalid protocol message.")
    return message
