"""Asynchronous sudo bootstrap and helper transport."""

import os
import stat
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from desktop_afk_alert.protocol import MAX_MESSAGE_BYTES, decode, encode

PASSWORD_PROMPT = "[desktop-afk-alert:password]"


def installed_helper() -> str:
    for candidate in ("/usr/libexec/desktop-afk-alert-helper", "/usr/local/libexec/desktop-afk-alert-helper"):
        path = Path(candidate)
        if not path.is_file():
            continue
        resolved = path.resolve()
        for component in (path, resolved, *resolved.parents, *path.parents):
            info = component.stat()
            if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise RuntimeError("The installed helper and its parent directories must be owned by root and not writable by other users.")
        if not os.access(resolved, os.X_OK):
            raise RuntimeError("The installed helper is not executable.")
        return str(path)
    raise RuntimeError("Install the distribution package, or run scripts/install-dev-helper.sh, before activating protection.")


class HelperClient(QObject):
    message = Signal(dict)
    failed = Signal(str)
    ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._stdout)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(750)
        self.heartbeat.timeout.connect(lambda: self.send("heartbeat"))
        self.bootstrap_timer = QTimer(self)
        self.bootstrap_timer.setSingleShot(True)
        self.bootstrap_timer.timeout.connect(lambda: self._fail("Administrator authentication timed out."))
        self.buffer = bytearray()
        self.stderr_buffer = ""
        self.prompt_count = 0
        self.password = ""
        self.configuration = {}
        self.ready = False
        self.expected_exit = False
        self.failure_reported = False

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start(self, helper: str, session: str, password: str, configuration: dict):
        if self.running:
            raise RuntimeError("A protection session is already running.")
        self.buffer.clear()
        self.stderr_buffer = ""
        self.prompt_count = 0
        self.password = password
        self.configuration = configuration
        self.ready = False
        self.expected_exit = False
        self.failure_reported = False
        environment = QProcessEnvironment()
        environment.insert("PATH", "/usr/bin:/bin")
        environment.insert("LANG", "C.UTF-8")
        self.process.setProcessEnvironment(environment)
        self.process.setProgram("/usr/bin/sudo")
        self.process.setArguments(["-k", "-S", "-p", PASSWORD_PROMPT, "--", helper, "--session", session])
        self.process.start()
        self.bootstrap_timer.start(45000)

    def send(self, kind: str, **values):
        if not self.ready or not self.running:
            return
        try:
            self.process.write(encode(kind, **values))
        except ValueError:
            self._fail("The helper request exceeded the protocol limit.")

    def _stdout(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        try:
            while b"\n" in self.buffer:
                line, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                message = decode(line)
                if message["type"] == "ready":
                    self.ready = True
                    self.bootstrap_timer.stop()
                    self.heartbeat.start()
                    self.send("configure", **self.configuration)
                elif message["type"] == "configured":
                    self.send("activate", password=self.password)
                    self.password = ""
                else:
                    if message["type"] == "authentication" and message.get("success") and message.get("purpose") == "release":
                        self.expected_exit = True
                    if message["type"] == "error" and message.get("fatal"):
                        self.failure_reported = True
                        self.failed.emit(message.get("message", "Protection has been stopped."))
                    else:
                        self.message.emit(message)
            if len(self.buffer) > MAX_MESSAGE_BYTES:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            self._fail("The installed helper returned an invalid message. Reinstall it.")

    def _stderr(self):
        self.stderr_buffer = (self.stderr_buffer + bytes(self.process.readAllStandardError()).decode(errors="replace"))[-8192:]
        prompts = self.stderr_buffer.count(PASSWORD_PROMPT)
        if prompts > self.prompt_count:
            self.prompt_count = prompts
            if prompts == 1 and self.password:
                self.process.write(self.password.encode() + b"\n")
            else:
                self._fail("sudo rejected the password. Check your password and administrator permissions.")

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._fail("Could not start sudo. Install sudo and the application helper.")

    def _fail(self, message: str):
        if not self.failure_reported:
            self.failure_reported = True
            self.failed.emit(message)
        self.stop()

    def stop(self):
        self.expected_exit = True
        self.password = ""
        self.heartbeat.stop()
        self.bootstrap_timer.stop()
        if self.running:
            self.process.closeWriteChannel()

    def _finished(self, _exit_code, _exit_status):
        self._stdout()
        self.heartbeat.stop()
        self.bootstrap_timer.stop()
        self.password = ""
        if not self.expected_exit and not self.failure_reported:
            self.failed.emit("The privileged helper stopped. Protection is no longer active. Check your sudo permissions and helper installation.")
        self.ready = False
        self.ended.emit()
