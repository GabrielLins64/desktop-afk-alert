"""Time-bounded camera capture isolated from the protection interface."""

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtMultimedia import QMediaDevices

from desktop_afk_alert.protocol import MAX_MESSAGE_BYTES, decode, encode


def cameras() -> dict[str, object]:
    return {bytes(device.id()).hex(): device for device in QMediaDevices.videoInputs()}


class CameraCapture(QObject):
    completed = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.path = ""
        self.buffer = bytearray()
        self.result = None
        self.generation = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._finish(None, "Camera capture timed out. Sending a text-only alert."))

    def take(self, camera_id: str, directory: str, incident_id: str):
        self.cancel()
        generation = self.generation
        try:
            folder = Path(directory).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            filename = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%z") + "_" + incident_id + ".jpg"
            self.path = str(folder / filename)
            process = QProcess(self)
            self.process = process
            request = encode("capture", camera_id=camera_id, path=self.path)
            process.started.connect(lambda: self._started(process, request, generation))
            process.readyReadStandardOutput.connect(lambda: self._read(process, generation))
            process.readyReadStandardError.connect(lambda: process.readAllStandardError())
            process.errorOccurred.connect(lambda error: self._error(process, error, generation))
            process.finished.connect(lambda *_args: self._ended(process, generation))
            arguments = ["--camera-worker"]
            if "__compiled__" not in globals() and not getattr(sys, "frozen", False):
                arguments = ["-m", "desktop_afk_alert", *arguments]
            self.timer.start(5000)
            process.start(sys.executable, arguments)
        except (OSError, RuntimeError, ValueError):
            self._finish(None, "Could not open the camera or photo directory. Sending a text-only alert.")

    def _started(self, process, request: bytes, generation: int):
        if generation == self.generation:
            process.write(request)
            process.closeWriteChannel()

    def _read(self, process, generation: int):
        if generation != self.generation or self.result is not None:
            return
        self.buffer.extend(bytes(process.readAllStandardOutput()))
        if len(self.buffer) > MAX_MESSAGE_BYTES:
            self._finish(None, "The camera returned an invalid response. Sending a text-only alert.")
            return
        if b"\n" not in self.buffer:
            return
        line, _separator, _remainder = self.buffer.partition(b"\n")
        try:
            result = decode(bytes(line))
            path, error = result.get("path"), result.get("error", "")
            if result["type"] != "photo" or (path is not None and path != self.path) or not isinstance(error, str):
                raise ValueError("Invalid camera response.")
            if path:
                os.chmod(path, 0o600)
        except (OSError, ValueError, TypeError, KeyError):
            self._finish(None, "The camera photo could not be read or saved privately. Sending a text-only alert.")
            return
        # Wait for normal exit so Qt can finish releasing the camera. Completing
        # here would kill the worker while its native objects are still alive.
        self.result = (path, error)

    def _error(self, process, error, generation: int):
        if generation == self.generation and error == QProcess.ProcessError.FailedToStart:
            self._finish(None, "Could not start camera capture. Sending a text-only alert.")
            process.deleteLater()

    def _ended(self, process, generation: int):
        if generation == self.generation:
            self._read(process, generation)
            if generation == self.generation:
                if self.result is not None and process.exitStatus() == QProcess.ExitStatus.NormalExit and process.exitCode() == 0:
                    self._finish(*self.result)
                else:
                    self._finish(None, "Camera capture stopped unexpectedly. Protection remains active; sending a text-only alert.")
        process.deleteLater()

    def _finish(self, path, error: str):
        self.cancel()
        self.completed.emit(path, error)

    def cancel(self):
        self.generation += 1
        self.timer.stop()
        self.buffer.clear()
        self.result = None
        process, self.process = self.process, None
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
