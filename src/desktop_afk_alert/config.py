"""Private user settings and Secret Service credentials."""

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlparse

from desktop_afk_alert.shortcuts import DEFAULT_SHORTCUT, validate_shortcut

APP_NAME = "desktop-afk-alert"
DEFAULT_MESSAGE = "GET AWAY FROM THIS COMPUTER! I'M TEXTING 911 RIGHT NOW."
SECRET_NAMES = ("discord_webhook", "telegram_token")


@dataclass
class Settings:
    message: str = ""
    shutdown_enabled: bool = False
    shutdown_delay: int = 60
    photo_enabled: bool = False
    camera_id: str = ""
    photo_directory: str = ""
    startup_delay: int = 5
    freeze_cursor: bool = False
    release_shortcut: list[int] = field(default_factory=lambda: DEFAULT_SHORTCUT.copy())
    discord_enabled: bool = False
    telegram_enabled: bool = False
    telegram_chat_id: str = ""

    @property
    def warning(self) -> str:
        return self.message.strip() or DEFAULT_MESSAGE


@dataclass
class Credentials:
    discord_webhook: str = ""
    telegram_token: str = ""


def config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME / "settings.json"


def load_settings() -> tuple[Settings, str]:
    path = config_path()
    if not path.exists():
        return Settings(), ""
    try:
        if path.stat().st_size > 65536:
            raise ValueError("Settings file is too large.")
        values = json.loads(path.read_text())
        if not isinstance(values, dict) or values.pop("version", None) != 1:
            raise ValueError("Unsupported settings version.")
        defaults = Settings()
        allowed = {item.name for item in fields(Settings)}
        values = {key: value for key, value in values.items() if key in allowed}
        for key, value in values.items():
            if type(value) is not type(getattr(defaults, key)):
                raise ValueError("Invalid settings value.")
        settings = Settings(**values)
        settings.release_shortcut = validate_shortcut(settings.release_shortcut)
        if not 0 <= settings.startup_delay <= 86400 or not 1 <= settings.shutdown_delay <= 86400:
            raise ValueError("Invalid delay in settings.")
        return settings, ""
    except (OSError, ValueError, TypeError):
        return Settings(), "Could not read saved settings. Defaults have been restored."


def save_settings(settings: Settings) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"version": 1, **asdict(settings)}, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def secret_backend():
    import secretstorage
    from keyring.backends.SecretService import Keyring
    from keyring.errors import KeyringLocked

    class UnlockedKeyring(Keyring):
        def get_preferred_collection(self):
            connection = secretstorage.dbus_init()
            try:
                collection = secretstorage.get_default_collection(connection)
                if collection.is_locked():
                    raise KeyringLocked("Unlock the system keyring before opening the application.")
                return collection
            except BaseException:
                connection.close()
                raise

        @staticmethod
        def unlock(item):
            if item.is_locked():
                raise KeyringLocked("The keyring item is locked.")

    backend = UnlockedKeyring()
    if backend.priority <= 0:
        raise RuntimeError("Secret Service is unavailable.")
    return backend


def load_credentials() -> tuple[Credentials, str]:
    try:
        backend = secret_backend()
        values = {name: backend.get_password(APP_NAME, name) or "" for name in SECRET_NAMES}
        return Credentials(**values), ""
    except Exception:
        return Credentials(), "System keyring unavailable. Credentials will be kept for this run only."


def save_credentials(credentials: Credentials, names: tuple[str, ...] = SECRET_NAMES) -> str:
    try:
        from keyring.errors import PasswordDeleteError

        backend = secret_backend()
        for name in names:
            value = getattr(credentials, name)
            if value:
                backend.set_password(APP_NAME, name, value)
            else:
                try:
                    backend.delete_password(APP_NAME, name)
                except PasswordDeleteError:
                    pass
        return ""
    except Exception:
        return "System keyring unavailable. Credentials will be kept for this run only."


def validate_settings(settings: Settings, credentials: Credentials, cameras: set[str]) -> dict[str, str]:
    errors = {}
    try:
        validate_shortcut(settings.release_shortcut)
    except ValueError as error:
        errors["release_shortcut"] = str(error)
    if not 0 <= settings.startup_delay <= 86400:
        errors["startup_delay"] = "Enter a delay between 0 and 86,400 seconds."
    if type(settings.freeze_cursor) is not bool:
        errors["freeze_cursor"] = "Choose whether the cursor should stay frozen while armed."
    if settings.shutdown_enabled and not 1 <= settings.shutdown_delay <= 86400:
        errors["shutdown_delay"] = "Enter a delay between 1 and 86,400 seconds."
    if settings.photo_enabled:
        if settings.camera_id not in cameras:
            errors["camera_id"] = "Select an available camera, or turn off camera photos."
        try:
            directory = Path(settings.photo_directory).expanduser()
            if not settings.photo_directory.strip() or not directory.is_absolute():
                raise ValueError
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, probe = tempfile.mkstemp(prefix=".afk-write-", dir=directory)
            os.close(fd)
            os.unlink(probe)
        except (OSError, ValueError):
            errors["photo_directory"] = "Choose an absolute, writable photo directory."
    if settings.discord_enabled:
        try:
            url = urlparse(credentials.discord_webhook)
            parts = url.path.strip("/").split("/")
            valid_path = len(parts) == 4 and parts[:2] == ["api", "webhooks"] and parts[2].isdigit() and bool(parts[3])
            valid_url = url.scheme == "https" and url.hostname in {"discord.com", "canary.discord.com", "ptb.discord.com"} and valid_path and not url.username and not url.password and url.port in {None, 443} and not url.fragment
        except ValueError:
            valid_url = False
        if not valid_url:
            errors["discord_webhook"] = "Enter a complete HTTPS Discord channel webhook URL."
    if settings.telegram_enabled:
        token_parts = credentials.telegram_token.split(":", 1)
        if len(token_parts) != 2 or not token_parts[0].isdigit() or not token_parts[1] or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in token_parts[-1]):
            errors["telegram_token"] = "Enter the bot token supplied by BotFather."
        chat = settings.telegram_chat_id.strip()
        if not re.fullmatch(r"-?[0-9]+|@[A-Za-z0-9_]+", chat):
            errors["telegram_chat_id"] = "Enter a numeric chat ID or a public channel username."
    return errors
