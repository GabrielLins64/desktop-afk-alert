"""Application entry point and unprivileged orchestration."""

import argparse
import json
import math
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from desktop_afk_alert import __version__
from desktop_afk_alert.camera import CameraCapture, cameras
from desktop_afk_alert.client import HelperClient, installed_helper
from desktop_afk_alert.config import config_path, load_settings, save_credentials, save_settings, validate_settings
from desktop_afk_alert.keyboard import NativeKeyboard
from desktop_afk_alert.notifications import Incident, Notifications
from desktop_afk_alert.overlays import Overlays
from desktop_afk_alert.protocol import State
from desktop_afk_alert.session import SessionInhibitor, current_session
from desktop_afk_alert.theme import STYLESHEET
from desktop_afk_alert.window import SettingsWindow


class Controller(QObject):
    credentials_saved = Signal(str, bool)

    def __init__(self, application: QApplication, window: SettingsWindow):
        super().__init__(application)
        self.application = application
        self.window = window
        self.client = HelperClient(self)
        self.inhibitor = SessionInhibitor(self)
        self.overlays = Overlays(self)
        self.camera = CameraCapture(self)
        self.notifications = Notifications(self)
        self.keyboard = None
        self.state = State.IDLE
        self.previous = State.IDLE
        self.settings = None
        self.credentials = None
        self.incident = None
        self.photo_incident = None
        self.notice = ""
        self.quitting = False
        self.exit_save_finished = False
        self.activation_pending = False
        self.window.activate_requested.connect(self.activate)
        self.window.cancel_requested.connect(self.cancel_countdown)
        self.window.close_requested.connect(self.close)
        self.client.message.connect(self.receive)
        self.client.failed.connect(self.abort)
        self.client.ended.connect(self.helper_ended)
        self.inhibitor.lost.connect(self.abort)
        self.overlays.display_lost.connect(self.abort)
        self.overlays.submitted.connect(self.authenticate)
        self.overlays.cancelled.connect(lambda: self.client.send("cancel_auth"))
        self.camera.completed.connect(self.photo_ready)
        self.notifications.delivered.connect(self.delivery_finished)
        self.credentials_saved.connect(self._saved)
        self.application.aboutToQuit.connect(self.cleanup)

    def persist(self, settings, credentials, quit_after=False):
        try:
            save_settings(settings)
        except OSError:
            self.window.status.setText("Could not save settings. Check configuration directory permissions.")
        names = self.window.credentials_to_save()
        if not names:
            if quit_after:
                QTimer.singleShot(0, lambda: self._saved("", True))
            return

        def work():
            warning = save_credentials(credentials, names)
            try:
                self.credentials_saved.emit(warning, quit_after)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _saved(self, warning: str, quit_after: bool):
        if warning:
            self.window.keyring_note.setText(warning)
        if quit_after:
            self.exit_save_finished = True
            self._try_quit()

    def _try_quit(self):
        if self.quitting and self.exit_save_finished and not self.client.running:
            self.application.quit()

    def activate(self):
        if self.activation_pending or self.client.running or self.state != State.IDLE:
            return
        settings, credentials = self.window.collect()
        errors = validate_settings(settings, credentials, set(cameras()))
        self.window.show_errors(errors)
        if errors:
            self.window.status.setText("Check the highlighted settings before activating.")
            return
        try:
            helper = installed_helper()
            session, seat, _kind = current_session()
            keyboard = NativeKeyboard(self.application.platformName(), seat)
        except (RuntimeError, OSError, ValueError) as error:
            self.window.status.setText(str(error))
            return
        dialog = QInputDialog(self.window)
        dialog.setWindowTitle("Activate protection")
        dialog.setLabelText("Enter your sudo password to activate protection.")
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.setOkButtonText("Authenticate")
        dialog.setCancelButtonText("Cancel")
        dialog.resize(450, 180)
        accepted = dialog.exec()
        password = dialog.textValue()
        dialog.setTextValue("")
        dialog.deleteLater()
        if not accepted or not password:
            keyboard.close()
            return
        if not password.isprintable() or len(password.encode("utf-16-le")) > 2048:
            keyboard.close()
            password = ""
            self.window.status.setText("Password entry supports printable XKB characters, up to 1,024 UTF-16 units. Control characters are not supported.")
            return
        try:
            keyboard.close()
            keyboard = NativeKeyboard(self.application.platformName(), seat)
            self.inhibitor.acquire()
        except (RuntimeError, OSError, ValueError) as error:
            keyboard.close()
            password = ""
            self.window.status.setText(str(error))
            return
        self.keyboard = keyboard
        self.settings, self.credentials = settings, credentials
        self.incident = None
        self.notice = ""
        self.activation_pending = True
        self.window.set_busy(True)
        self.window.badge.setText("AUTHENTICATING")
        self.window.status.setText("Checking administrator permissions and password…")
        self.persist(settings, credentials)
        configuration = {"startup_delay": settings.startup_delay, "shutdown_enabled": settings.shutdown_enabled, "shutdown_delay": settings.shutdown_delay, "release_shortcut": settings.release_shortcut}
        self.client.start(helper, session, password, configuration)
        password = ""

    def receive(self, message: dict):
        kind = message["type"]
        if self.quitting:
            return
        if kind == "state":
            self._state(message)
        elif kind == "keyboard_state" and self.keyboard:
            self.keyboard.set_locks(message.get("caps_lock", False), message.get("num_lock", False))
        elif kind == "input" and self.keyboard:
            action, text = self.keyboard.translate(message["code"], message["value"], message["down"])
            if message.get("typing") and self.state == State.AUTHENTICATING:
                self.overlays.handle_key(action, text, self.keyboard.layout_name)
        elif kind == "authenticate":
            self.state = State.AUTHENTICATING
            self.previous = State(message["previous"])
            self.keyboard.reset_compose()
            warning = self.settings.warning if self.previous == State.FROZEN else "PROTECTED DESKTOP"
            self.overlays.show_auth(self.keyboard.layout_name, warning)
        elif kind == "incident":
            self._incident(message["trigger"])
        elif kind == "authentication":
            if not message.get("success") and message.get("purpose") == "activate":
                self.abort(message.get("message", "Password authentication failed."))
            elif message.get("success") and message.get("purpose") == "activate":
                self.activation_pending = False
            elif message.get("success") and message.get("purpose") == "release":
                self.client.expected_exit = True
        elif kind == "error":
            self.notice = message.get("message", "A background operation failed.")
            self.window.status.setText(self.notice)

    def _state(self, message: dict):
        state = State(message["state"])
        if state == State.IDLE and self.activation_pending:
            return
        previous = self.state
        self.state = state
        self.window.protection_active = state in {State.ARMED, State.FROZEN, State.AUTHENTICATING}
        self.window.badge.setText({State.IDLE: "READY", State.COUNTDOWN: "ARMING", State.ARMED: "ARMED", State.FROZEN: "INTRUSION", State.AUTHENTICATING: "PASSWORD REQUIRED"}[state])
        detail = message.get("detail", "")
        if detail:
            self.notice = detail
        if state == State.COUNTDOWN:
            remaining = math.ceil(message.get("startup_remaining") or 0)
            self.window.set_busy(True, countdown=True)
            self.window.status.setText(detail or f"Arming in {remaining} seconds. Step away from your keyboard and mouse.")
        elif state in {State.ARMED, State.FROZEN, State.AUTHENTICATING}:
            self.window.set_busy(True)
            if state == State.ARMED:
                if previous != State.ARMED:
                    self.window.showMinimized()
            else:
                self.window.hide()
            if previous == State.AUTHENTICATING and state != State.AUTHENTICATING:
                self.overlays.end_auth(state == State.FROZEN)
            if state == State.FROZEN and not self.overlays.visible:
                self.overlays.show_warning(self.settings.warning)
            self.overlays.set_status(message.get("shutdown_remaining"), paused=state == State.AUTHENTICATING,
                                     requested=message.get("shutdown_requested", False) and not message.get("shutdown_failed", False), detail=detail or self.notice,
                                     busy=message.get("auth_busy", False))
        elif state == State.IDLE:
            self.finish("Protection disabled.")

    def _incident(self, trigger: str):
        if self.incident is not None:
            return
        self.incident = Incident.create(trigger, self.settings.warning)
        self.window.protection_active = True
        self.window.hide()
        self.overlays.show_warning(self.settings.warning)
        if self.settings.photo_enabled:
            if self.photo_incident is not None:
                self.camera.cancel()
                self.photo_ready(None, "The previous camera capture was interrupted. Its alert was sent without a photo.")
            self.photo_incident = (self.settings, self.credentials, self.incident)
            self.camera.take(self.settings.camera_id, self.settings.photo_directory, self.incident.identifier)
        else:
            self.notifications.send(self.settings, self.credentials, self.incident, None)

    def photo_ready(self, path, error: str):
        context, self.photo_incident = self.photo_incident, None
        if context is None:
            return
        settings, credentials, incident = context
        if path and self.incident is incident and self.overlays.visible:
            self.overlays.set_photo(path)
        if error:
            self.notice = error
            self.window.status.setText(error)
        self.notifications.send(settings, credentials, incident, path)

    def delivery_finished(self, provider, message):
        self.notice = f"{provider}: {message}"
        if self.state == State.IDLE:
            self.window.status.setText(self.notice)

    def authenticate(self, password: str):
        self.client.send("authenticate", password=password)

    def cancel_countdown(self):
        if self.state == State.COUNTDOWN:
            self.client.expected_exit = True
            self.client.send("cancel_countdown")
            self.client.stop()

    def abort(self, message: str):
        self.client.stop()
        self.activation_pending = False
        self.finish(message)

    def helper_ended(self):
        if self.quitting:
            self._try_quit()
        else:
            if self.state == State.COUNTDOWN:
                self.finish("Activation cancelled.")
            elif self.state != State.IDLE or self.activation_pending:
                self.activation_pending = False
                self.finish("Protection disabled. " + self.notice if self.notice else "Protection disabled.")

    def finish(self, message: str):
        self.state = State.IDLE
        self.activation_pending = False
        self.window.protection_active = False
        self.overlays.dismiss()
        self.inhibitor.release()
        if self.keyboard:
            self.keyboard.close()
            self.keyboard = None
        self.window.set_busy(False)
        self.window.badge.setText("READY")
        self.window.status.setText(message)
        if self.window.isMinimized():
            self.window.showNormal()
        else:
            self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def close(self):
        if self.window.protection_active:
            return
        self.quitting = True
        self.cleanup()
        settings, credentials = self.window.collect()
        self.persist(settings, credentials, quit_after=True)
        QTimer.singleShot(5000, self.application.quit)

    def cleanup(self):
        self.client.stop()
        self.inhibitor.release()
        self.overlays.dismiss()
        self.camera.cancel()
        if self.keyboard:
            self.keyboard.close()
            self.keyboard = None

    def exception_hook(self, exception_type, _exception, _traceback):
        print(f"Desktop AFK Alert stopped after an internal {exception_type.__name__}. No request data was logged.", file=sys.stderr)
        self.abort("An internal error stopped protection. Input devices are being released; restart the application before activating again.")


def diagnose(application: QApplication) -> int:
    report = {"version": __version__, "qt_platform": application.platformName(), "configuration": str(config_path())}
    okay = True
    try:
        report["helper"] = installed_helper()
    except RuntimeError as error:
        report["helper_error"] = str(error)
        okay = False
    try:
        session, seat, kind = current_session()
        report.update(session=session, seat=seat, session_type=kind)
        keyboard = NativeKeyboard(application.platformName(), seat)
        report["keyboard_layout"] = keyboard.layout_name
        keyboard.close()
    except (OSError, RuntimeError, ValueError) as error:
        report["session_error"] = str(error)
        okay = False
    report["cameras"] = [device.description() for device in cameras().values()]
    print(json.dumps(report, indent=2))
    return 0 if okay else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep your desktop visible. Warn unexpected visitors.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--diagnose", action="store_true", help="Read environment information without capturing input or activating protection")
    arguments = parser.parse_args()
    if not sys.platform.startswith("linux"):
        print("Desktop AFK Alert currently supports Linux only.", file=sys.stderr)
        return 1
    if os.getuid() == 0 or os.geteuid() == 0:
        print("Run the application as your normal desktop user. Only its helper runs as root.", file=sys.stderr)
        return 1
    os.umask(0o077)
    application = QApplication([sys.argv[0]])
    application.setApplicationName("desktop-afk-alert")
    application.setApplicationDisplayName("Desktop AFK Alert")
    application.setOrganizationName("desktop-afk-alert")
    application.setApplicationVersion(__version__)
    application.setDesktopFileName("desktop-afk-alert")
    application.setStyle("Fusion")
    application.setStyleSheet(STYLESHEET)
    application.setQuitOnLastWindowClosed(False)
    if arguments.diagnose:
        return diagnose(application)
    runtime = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation)
    if not runtime:
        print("A desktop runtime directory is required (XDG_RUNTIME_DIR).", file=sys.stderr)
        return 1
    lock = QLockFile(str(Path(runtime) / "desktop-afk-alert.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "Desktop AFK Alert is running", "Use your configured release shortcut and sudo password to return to settings.")
        return 0
    icon_path = Path(__file__).with_name("icon.svg")
    if not icon_path.exists():
        icon_path = Path(__file__).resolve().parents[2] / "resources" / "desktop-afk-alert.svg"
    icon = QIcon(str(icon_path))
    application.setWindowIcon(icon)
    settings, warning = load_settings()
    window = SettingsWindow(settings, warning, icon)
    controller = Controller(application, window)
    sys.excepthook = controller.exception_hook
    window.show()
    QTimer.singleShot(0, window.load_secrets)
    try:
        return application.exec()
    finally:
        controller.cleanup()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
