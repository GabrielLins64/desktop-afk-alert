"""Single-use, unprivileged Qt camera worker. Native failures stay in this process."""

import os
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtMultimedia import QCamera, QImageCapture, QMediaCaptureSession, QMediaDevices, QVideoSink

from desktop_afk_alert.protocol import MAX_MESSAGE_BYTES, decode, encode

WARMUP_MS = 2000
MINIMUM_FRAMES = 5


class Snapshot(QObject):
    def __init__(self, application):
        super().__init__(application)
        self.application = application
        self.camera = None
        self.session = None
        self.capture = None
        self.sink = None
        self.path = ""
        self.frames = 0
        self.settled = False
        self.requested = False
        self.done = False
        self.warmup = QTimer(self)
        self.warmup.setSingleShot(True)
        self.warmup.timeout.connect(self._settled)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self.finish(None, "Camera capture timed out. Sending a text-only alert."))

    def start(self, camera_id: str, path: str):
        try:
            device = next((device for device in QMediaDevices.videoInputs() if bytes(device.id()).hex() == camera_id), None)
            if device is None:
                self.finish(None, "The selected camera is unavailable. Sending a text-only alert.")
                return
            self.path = path
            self.camera = QCamera(device, self)
            self.session = QMediaCaptureSession(self)
            self.capture = QImageCapture(self)
            self.capture.setFileFormat(QImageCapture.FileFormat.JPEG)
            self.capture.setQuality(QImageCapture.Quality.HighQuality)
            self.sink = QVideoSink(self)
            self.session.setCamera(self.camera)
            self.session.setImageCapture(self.capture)
            self.session.setVideoSink(self.sink)
            self.capture.readyForCaptureChanged.connect(lambda _ready: self._capture_when_ready())
            self.capture.imageSaved.connect(lambda _identifier, saved: self.finish(saved, ""))
            self.capture.errorOccurred.connect(self._error)
            self.camera.errorOccurred.connect(self._error)
            self.sink.videoFrameChanged.connect(self._frame)
            if self.camera.isExposureModeSupported(QCamera.ExposureMode.ExposureAuto):
                self.camera.setExposureMode(QCamera.ExposureMode.ExposureAuto)
            if self.camera.supportedFeatures() & QCamera.Feature.ManualExposureTime:
                self.camera.setAutoExposureTime()
            self.deadline.start(4500)
            self.camera.start()
        except (OSError, RuntimeError):
            self.finish(None, "Could not open the camera. Sending a text-only alert.")

    def _frame(self, frame):
        if self.done or not frame.isValid():
            return
        self.frames += 1
        if self.frames == 1:
            self.warmup.start(WARMUP_MS)
        self._capture_when_ready()

    def _settled(self):
        self.settled = True
        self._capture_when_ready()

    def _capture_when_ready(self):
        if self.done or self.requested or not self.settled or self.frames < MINIMUM_FRAMES:
            return
        if self.capture is not None and self.capture.isReadyForCapture():
            self.requested = True
            # Leave the native frame callback before requesting a still image.
            QTimer.singleShot(0, self._capture)

    def _capture(self):
        if not self.done and self.capture.captureToFile(self.path) < 0:
            self._error()

    def _error(self, *_args):
        self.finish(None, "Camera capture failed. Check camera permissions and whether another application is using it.")

    def finish(self, path, error: str):
        if self.done:
            return
        self.done = True
        self.deadline.stop()
        self.warmup.stop()
        try:
            if path:
                os.chmod(path, 0o600)
        except OSError:
            path, error = None, "The camera photo could not be saved privately. Sending a text-only alert."
        sys.stdout.buffer.write(encode("photo", path=path, error=error))
        sys.stdout.buffer.flush()
        # Do not stop or detach the camera from inside a native capture callback.
        QTimer.singleShot(0, self.application.quit)


def main() -> int:
    try:
        request = decode(sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1))
        if request["type"] != "capture" or not isinstance(request.get("camera_id"), str) or not isinstance(request.get("path"), str):
            return 1
    except (OSError, ValueError, TypeError, KeyError):
        return 1
    application = QGuiApplication([sys.argv[0]])
    worker = Snapshot(application)
    QTimer.singleShot(0, lambda: worker.start(request["camera_id"], request["path"]))
    return application.exec()
