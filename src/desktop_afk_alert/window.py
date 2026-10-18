"""Settings window. All privileged actions are delegated to the controller."""

import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from desktop_afk_alert.camera import cameras
from desktop_afk_alert.config import Credentials, DEFAULT_MESSAGE, Settings, load_credentials
from desktop_afk_alert.shortcuts import shortcut_label
from desktop_afk_alert.widgets import ShortcutRecorder, Switch


def label(text: str, role: str = "", wrap=False) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(wrap)
    return widget


class SettingsWindow(QMainWindow):
    activate_requested = Signal()
    cancel_requested = Signal()
    close_requested = Signal()
    credentials_loaded = Signal(object, str)

    def __init__(self, settings: Settings, load_error: str, icon: QIcon):
        super().__init__()
        self.settings = settings
        self.icon = icon
        self.release_shortcut = settings.release_shortcut.copy()
        self.protection_active = False
        self.credentials_ready = False
        self.credentials_readable = False
        self.errors = {}
        self.fields = {}
        self.setWindowTitle("Desktop AFK Alert")
        self.setWindowIcon(icon)
        self.setMinimumSize(488, 428)
        available = self.screen().availableGeometry()
        self.resize(round(min(950, available.width() - 60) * 0.75), round(min(900, available.height() - 70) * 0.75))
        self._center_on_first_show = True
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll, 1)
        content = QWidget()
        self.scroll.setWidget(content)
        body = QVBoxLayout(content)
        body.setContentsMargins(30, 28, 30, 28)
        body.setSpacing(18)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon.pixmap(58, 58))
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(label("DESKTOP AFK ALERT", "brand"))
        titles.addWidget(label("Step away. Keep your desktop visible.", "muted"))
        header.addLayout(titles, 1)
        self.badge = label("READY", "badge")
        header.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(header)

        protection = self.card(body, "01 / PROTECTION", "Your desktop. Your boundaries.")
        self.message = QPlainTextEdit(settings.message)
        self.message.setObjectName("messageInput")
        self.message.setPlaceholderText(DEFAULT_MESSAGE)
        self.message.setFixedHeight(95)
        self.message.setAccessibleName("Warning message")
        self.field(protection, "message", "Warning message", self.message, "Leave blank to use the default. The warning is displayed in uppercase.")
        timing = QHBoxLayout()
        timing.addWidget(label("Startup delay"), 1)
        self.startup = self.seconds(settings.startup_delay, 0)
        self.startup.setAccessibleName("Startup delay in seconds")
        timing.addWidget(self.startup)
        protection.addLayout(timing)
        self.register_error(protection, "startup_delay", self.startup)

        shortcut_row = QHBoxLayout()
        shortcut_row.addWidget(label("Release shortcut"), 1)
        self.shortcut = QPushButton(shortcut_label(self.release_shortcut))
        self.shortcut.setObjectName("secondary")
        self.shortcut.setToolTip("Record 1–3 simultaneous keys")
        self.shortcut.clicked.connect(self.record_shortcut)
        shortcut_row.addWidget(self.shortcut)
        protection.addLayout(shortcut_row)
        protection.addWidget(label("Required to disarm. Your sudo password is also required.", "muted", True))
        self.register_error(protection, "release_shortcut", self.shortcut)

        self.shutdown_switch = self.switch_row(protection, "Shut down computer", "Start a shutdown countdown when unexpected input is detected.", settings.shutdown_enabled)
        shutdown_row = QHBoxLayout()
        self.shutdown_label = label("Shutdown delay")
        shutdown_row.addWidget(self.shutdown_label, 1)
        self.shutdown_delay = self.seconds(settings.shutdown_delay, 1)
        self.shutdown_delay.setAccessibleName("Shutdown delay in seconds")
        shutdown_row.addWidget(self.shutdown_delay)
        protection.addLayout(shutdown_row)
        self.register_error(protection, "shutdown_delay", self.shutdown_delay)
        self.shutdown_switch.toggled.connect(self._shutdown_toggled)
        self._shutdown_toggled(self.shutdown_switch.isChecked())

        photo = self.card(body, "02 / CAMERA", "A single snapshot when the warning appears.")
        self.photo_switch = self.switch_row(photo, "Take camera photo", "Save a photo locally and attach it to enabled alerts.", settings.photo_enabled)
        self.photo_fields = QWidget()
        self.photo_fields.setObjectName("cardContent")
        photo_layout = QVBoxLayout(self.photo_fields)
        photo_layout.setContentsMargins(0, 4, 0, 0)
        photo_layout.setSpacing(10)
        photo.addWidget(self.photo_fields)
        camera_row = QHBoxLayout()
        self.camera = QComboBox()
        self.camera.setAccessibleName("Camera")
        camera_row.addWidget(self.camera, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_cameras)
        camera_row.addWidget(refresh)
        photo_layout.addWidget(label("Camera"))
        photo_layout.addLayout(camera_row)
        self.register_error(photo_layout, "camera_id", self.camera)
        photo_layout.addWidget(label("Photo directory"))
        directory_row = QHBoxLayout()
        pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation) or str(Path.home() / "Pictures")
        self.directory = QLineEdit(settings.photo_directory or str(Path(pictures) / "desktop-afk-alert"))
        self.directory.setAccessibleName("Photo directory")
        directory_row.addWidget(self.directory, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_directory)
        directory_row.addWidget(browse)
        photo_layout.addLayout(directory_row)
        self.register_error(photo_layout, "photo_directory", self.directory)
        self.photo_switch.toggled.connect(self.photo_fields.setVisible)
        self.photo_fields.setVisible(settings.photo_enabled)
        self.media_devices = QMediaDevices(self)
        self.media_devices.videoInputsChanged.connect(self.refresh_cameras)
        self.refresh_cameras()

        alerts = self.card(body, "03 / REMOTE ALERTS", "A heads-up, wherever you are.")
        self.discord_switch = self.switch_row(alerts, "Discord", "Send the warning and optional photo to a channel webhook.", settings.discord_enabled)
        self.discord_fields = QWidget()
        self.discord_fields.setObjectName("cardContent")
        discord_layout = QVBoxLayout(self.discord_fields)
        discord_layout.setContentsMargins(0, 4, 0, 0)
        self.webhook = self.secret_input("https://discord.com/api/webhooks/…", "Discord webhook URL")
        self.field(discord_layout, "discord_webhook", "Channel webhook URL", self.webhook)
        alerts.addWidget(self.discord_fields)
        self.discord_switch.toggled.connect(self.discord_fields.setVisible)
        self.discord_fields.setVisible(settings.discord_enabled)

        self.telegram_switch = self.switch_row(alerts, "Telegram", "Send the warning and optional photo through your bot.", settings.telegram_enabled)
        self.telegram_fields = QWidget()
        self.telegram_fields.setObjectName("cardContent")
        telegram_layout = QVBoxLayout(self.telegram_fields)
        telegram_layout.setContentsMargins(0, 4, 0, 0)
        self.bot_token = self.secret_input("Token from @BotFather", "Telegram bot token")
        self.chat_id = QLineEdit(settings.telegram_chat_id)
        self.chat_id.setPlaceholderText("For example: -1001234567890")
        self.chat_id.setAccessibleName("Telegram chat ID")
        self.field(telegram_layout, "telegram_token", "Bot token", self.bot_token)
        self.field(telegram_layout, "telegram_chat_id", "Chat ID", self.chat_id)
        alerts.addWidget(self.telegram_fields)
        self.telegram_switch.toggled.connect(self.telegram_fields.setVisible)
        self.telegram_fields.setVisible(settings.telegram_enabled)
        self.keyring_note = label("Credentials are stored in your system keyring.", "muted", True)
        alerts.addWidget(self.keyring_note)

        body.addWidget(label("GNOME + KDE  /  X11 + WAYLAND", "eyebrow"))
        body.addStretch()

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(30, 17, 30, 17)
        footer_layout.setSpacing(16)
        self.status = label(load_error or "Configure your guard, then activate when you step away.", "status", True)
        footer_layout.addWidget(self.status, 1)
        self.cancel = QPushButton("Cancel countdown")
        self.cancel.setVisible(False)
        self.cancel.clicked.connect(self.cancel_requested)
        footer_layout.addWidget(self.cancel)
        self.activate = QPushButton("Activate")
        self.activate.setObjectName("activate")
        self.activate.setMinimumWidth(145)
        self.activate.clicked.connect(self.activate_requested)
        footer_layout.addWidget(self.activate)
        outer.addWidget(footer)
        self.credentials_loaded.connect(self._credentials_loaded)

    def showEvent(self, event):
        super().showEvent(event)
        if self._center_on_first_show:
            self._center_on_first_show = False
            QTimer.singleShot(0, self._center_on_screen)

    def _center_on_screen(self):
        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

    def card(self, body, eyebrow: str, title: str):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(21, 18, 21, 20)
        layout.setSpacing(12)
        layout.addWidget(label(eyebrow, "eyebrow"))
        layout.addWidget(label(title, "sectionTitle"))
        body.addWidget(frame)
        return layout

    def register_error(self, layout, name: str, control):
        error = label("", "error", True)
        error.setVisible(False)
        layout.addWidget(error)
        self.errors[name] = error
        self.fields[name] = control

    def field(self, layout, name, title, control, hint=""):
        caption = label(title)
        caption.setBuddy(control)
        layout.addWidget(caption)
        layout.addWidget(control)
        if hint:
            layout.addWidget(label(hint, "muted", True))
        self.register_error(layout, name, control)

    def switch_row(self, layout, title, description, checked):
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(4)
        copy.addWidget(label(title))
        copy.addWidget(label(description, "muted", True))
        row.addLayout(copy, 1)
        switch = Switch(title, checked)
        row.addWidget(switch)
        layout.addLayout(row)
        return switch

    def seconds(self, value, minimum):
        spin = QSpinBox()
        spin.setRange(minimum, 86400)
        spin.setValue(value)
        spin.setSuffix(" s")
        spin.setToolTip("Type seconds, or use the arrow keys.")
        return spin

    def secret_input(self, placeholder, accessible):
        control = QLineEdit()
        control.setEchoMode(QLineEdit.EchoMode.Password)
        control.setPlaceholderText(placeholder)
        control.setAccessibleName(accessible)
        control.setMaxLength(4096)
        return control

    def _shutdown_toggled(self, enabled):
        self.shutdown_delay.setEnabled(enabled)
        self.shutdown_label.setEnabled(enabled)

    def refresh_cameras(self):
        selected = self.camera.currentData() or self.settings.camera_id
        self.camera.clear()
        available = cameras()
        for identifier, device in available.items():
            self.camera.addItem(device.description(), identifier)
        index = self.camera.findData(selected)
        if index >= 0:
            self.camera.setCurrentIndex(index)
        elif selected:
            self.camera.addItem("Unavailable camera — choose another or refresh", selected)
            self.camera.setCurrentIndex(self.camera.count() - 1)
        elif not available:
            self.camera.addItem("No cameras found", "")

    def browse_directory(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose photo directory", self.directory.text(), QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog)
        if selected:
            self.directory.setText(selected)

    def record_shortcut(self):
        recorder = ShortcutRecorder(self.release_shortcut, self)
        if recorder.exec() == QDialog.DialogCode.Accepted:
            self.release_shortcut = recorder.result_keys
            self.shortcut.setText(shortcut_label(self.release_shortcut))

    def collect(self) -> tuple[Settings, Credentials]:
        settings = Settings(
            message=self.message.toPlainText(), shutdown_enabled=self.shutdown_switch.isChecked(),
            shutdown_delay=self.shutdown_delay.value(), photo_enabled=self.photo_switch.isChecked(),
            camera_id=self.camera.currentData() or "", photo_directory=self.directory.text().strip(),
            startup_delay=self.startup.value(), release_shortcut=self.release_shortcut.copy(),
            discord_enabled=self.discord_switch.isChecked(), telegram_enabled=self.telegram_switch.isChecked(),
            telegram_chat_id=self.chat_id.text().strip(),
        )
        return settings, Credentials(self.webhook.text().strip(), self.bot_token.text().strip())

    def show_errors(self, errors: dict[str, str]):
        for name, error in self.errors.items():
            message = errors.get(name, "")
            error.setText(message)
            error.setVisible(bool(message))
            control = self.fields[name]
            control.setProperty("invalid", bool(message))
            control.style().unpolish(control)
            control.style().polish(control)
        if errors:
            first = next((name for name in self.fields if name in errors), None)
            if first:
                self.scroll.ensureWidgetVisible(self.fields[first], 20, 40)
                self.fields[first].setFocus()

    def set_busy(self, busy: bool, countdown=False):
        self.scroll.setEnabled(not busy)
        self.activate.setEnabled(not busy)
        self.cancel.setVisible(countdown)

    def load_secrets(self):
        def work():
            credentials, warning = load_credentials()
            try:
                self.credentials_loaded.emit(credentials, warning)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _credentials_loaded(self, credentials: Credentials, warning: str):
        for control, value in ((self.webhook, credentials.discord_webhook), (self.bot_token, credentials.telegram_token)):
            if not control.isModified():
                control.setText(value)
        self.credentials_ready = True
        self.credentials_readable = not warning
        if warning:
            self.keyring_note.setText(warning)

    def credentials_to_save(self) -> tuple[str, ...]:
        return tuple(name for name, control in (("discord_webhook", self.webhook), ("telegram_token", self.bot_token)) if self.credentials_readable or control.isModified())

    def closeEvent(self, event):
        if self.protection_active:
            event.ignore()
        else:
            self.close_requested.emit()
            event.accept()
