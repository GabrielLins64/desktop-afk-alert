"""Private, rotating application logs with credential-safe formatting."""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "desktop_afk_alert"
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
BOT_TOKEN_PATTERN = re.compile(r"\b[0-9]{5,}:[A-Za-z0-9_-]{20,}\b")


def log_path() -> Path:
    default = Path.home() / ".local" / "state"
    state = Path(os.environ.get("XDG_STATE_HOME") or default).expanduser()
    if not state.is_absolute():
        state = default
    return state / "desktop-afk-alert" / "logs" / "desktop-afk-alert.log"


class PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        descriptor = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            return os.fdopen(descriptor, "a", encoding="utf-8", errors="backslashreplace")
        except BaseException:
            os.close(descriptor)
            raise


class SafeFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        message = URL_PATTERN.sub("[redacted URL]", message)
        return BOT_TOKEN_PATTERN.sub("[redacted token]", message)


def configure_logging() -> Path:
    logger = logging.getLogger(LOGGER_NAME)
    path = log_path()
    if logger.handlers:
        return path
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = SafeFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S%z")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    # HTTP client request logs can include webhook URLs and Telegram bot tokens.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        file_handler = PrivateRotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as error:
        logger.warning("Could not open the application log file (%s). Console logging remains available.", type(error).__name__)
        return path
    logger.info("Application logging started. Log file: %s", path)
    return path
