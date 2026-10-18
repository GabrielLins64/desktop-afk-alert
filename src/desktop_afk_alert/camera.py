"""One asynchronous, time-bounded camera snapshot per incident."""

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QCamera, QImageCapture, QMediaCaptureSession, QMediaDevices, QVideoSink


def cameras() -> dict[str, object]:
    return {bytes(device.id()).hex(): device for device in QMediaDevices.videoInputs()}


class CameraCapture(QObject):
    completed = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera = None
        self.session = None
        self.capture = None
        self.sink = None
        self.requested = False
        self.path = ""
        self.generation = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._finish(None, "Camera capture timed out. Sending a text-only alert."))

    def take(self, camera_id: str, directory: str, incident_id: str):
        self.cancel()
        generation = self.generation
        available = cameras()
        device = available.get(camera_id)
        if device is None:
            self.completed.emit(None, "The selected camera is unavailable. Sending a text-only alert.")
            return
        try:
            folder = Path(directory).expanduser()
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            filename = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%z") + "_" + incident_id + ".jpg"
            self.path = str(folder / filename)
            self.camera = QCamera(device, self)
            self.session = QMediaCaptureSession(self)
            self.capture = QImageCapture(self)
            self.capture.setFileFormat(QImageCapture.FileFormat.JPEG)
            self.capture.setQuality(QImageCapture.Quality.HighQuality)
            self.sink = QVideoSink(self)
            self.session.setCamera(self.camera)
            self.session.setImageCapture(self.capture)
            self.session.setVideoSink(self.sink)
            self.requested = False
            self.capture.readyForCaptureChanged.connect(lambda ready: self._ready(ready, generation))
            self.capture.imageSaved.connect(lambda _identifier, path: self._saved(path, generation))
            self.capture.errorOccurred.connect(lambda *_args: self._error(generation))
            self.camera.errorOccurred.connect(lambda *_args: self._error(generation))
            self.timer.start(5000)
            self.camera.start()
            self._ready(self.capture.isReadyForCapture(), generation)
        except (OSError, RuntimeError):
            self._finish(None, "Could not open the camera or photo directory. Sending a text-only alert.")

    def _ready(self, ready: bool, generation: int):
        if generation == self.generation and ready and not self.requested and self.capture is not None:
            self.requested = True
            if self.capture.captureToFile(self.path) < 0:
                self._error(generation)

    def _saved(self, path: str, generation: int):
        if generation != self.generation:
            return
        try:
            os.chmod(path, 0o600)
            self._finish(path, "")
        except OSError:
            self._finish(None, "The camera photo could not be saved privately. Sending a text-only alert.")

    def _error(self, generation: int):
        if generation == self.generation:
            self._finish(None, "Camera capture failed. Check camera permissions and whether another application is using it.")

    def _finish(self, path, error: str):
        self.cancel()
        self.completed.emit(path, error)

    def cancel(self):
        self.generation += 1
        self.timer.stop()
        if self.camera is not None:
            self.camera.stop()
        if self.session is not None:
            self.session.setCamera(None)
            self.session.setImageCapture(None)
            self.session.setVideoSink(None)
        for item in (self.capture, self.camera, self.sink, self.session):
            if item is not None:
                item.deleteLater()
        self.camera = self.capture = self.sink = self.session = None
