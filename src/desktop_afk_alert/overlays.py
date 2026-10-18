"""Per-monitor warning surfaces and a locally edited password field."""

import math

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QVBoxLayout, QWidget


class PasswordPanel(QFrame):
    submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("passwordPanel")
        self.busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        title = QLabel("AUTHENTICATION REQUIRED")
        title.setObjectName("eyebrow")
        layout.addWidget(title)
        self.layout_label = QLabel()
        self.layout_label.setObjectName("muted")
        self.layout_label.setWordWrap(True)
        layout.addWidget(self.layout_label)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setReadOnly(True)
        self.password.setMaxLength(1024)
        self.password.setAccessibleName("Sudo password")
        self.password.setPlaceholderText("Your sudo password")
        self.password.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.password)
        self.hint = QLabel("Enter to unlock  ·  Esc to cancel  ·  Shutdown is paused")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    def begin(self, layout_name: str):
        self.busy = False
        self.password.clear()
        self.layout_label.setText("Keyboard: " + layout_name)
        self.hint.setText("Enter to unlock  ·  Esc to cancel  ·  Shutdown is paused")
        self.show()
        self.password.setFocus()

    def set_busy(self, busy: bool, detail=""):
        self.busy = busy
        if busy:
            self.password.clear()
            self.hint.setText(detail or "Checking password…")

    def handle_key(self, action: str, text: str):
        if action == "cancel":
            self.password.clear()
            self.cancelled.emit()
            return
        if self.busy:
            return
        value = self.password.text()
        position = len(value.encode("utf-16-le")[:self.password.cursorPosition() * 2].decode("utf-16-le", errors="ignore"))
        if action == "submit":
            if value:
                self.password.clear()
                self.busy = True
                self.hint.setText("Checking password…")
                self.submitted.emit(value)
        elif action == "backspace" and position:
            self.set_value(value[:position - 1] + value[position:], position - 1)
        elif action == "delete":
            self.set_value(value[:position] + value[position + 1:], position)
        elif action in {"left", "right", "home", "end"}:
            target = {"left": position - 1, "right": position + 1, "home": 0, "end": len(value)}[action]
            self.set_value(value, max(0, min(len(value), target)))
        elif text and len((value + text).encode("utf-16-le")) // 2 <= 1024:
            self.set_value(value[:position] + text + value[position:], position + len(text))

    def set_value(self, value: str, position: int):
        self.password.setText(value)
        self.password.setCursorPosition(len(value[:position].encode("utf-16-le")) // 2)


class WarningWindow(QWidget):
    def __init__(self, screen):
        super().__init__()
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if QApplication.platformName() == "xcb":
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.setWindowTitle("Desktop AFK Alert — Protected")
        self.setStyleSheet("WarningWindow { background: #000000; }")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.screen_target = screen
        self.allow_close = False
        self.message = ""
        self.photo = QImage()
        self.footer = ""
        self.panel = PasswordPanel(self)
        self.panel.hide()
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self.showFullScreen()

    def resizeEvent(self, event):
        self.place_panel()
        super().resizeEvent(event)

    def place_panel(self):
        width = min(590, max(260, self.width() - 48))
        height = self.panel.sizeHint().height()
        self.panel.setGeometry((self.width() - width) // 2, self.height() - height - 48, width, height)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        margin = max(20, min(self.width(), self.height()) // 18)
        bottom = self.panel.height() + 80 if self.panel.isVisible() else 52
        usable = QRect(margin, margin, max(1, self.width() - margin * 2), max(1, self.height() - margin - bottom))
        photo_height = min(int(usable.height() * 0.42), 360) if not self.photo.isNull() else 0
        text_box = QRect(usable.x(), usable.y(), usable.width(), max(1, usable.height() - photo_height - (20 if photo_height else 0)))
        text = self.message.upper()
        font = QFont("DejaVu Sans Mono")
        font.setBold(True)
        alignment = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        low, high, chosen = 1, min(100, max(24, self.width() // 14)), 1
        while low <= high:
            size = (low + high) // 2
            font.setPixelSize(size)
            bounds = QFontMetrics(font).boundingRect(QRect(0, 0, text_box.width(), 100000), alignment, text)
            if bounds.height() <= text_box.height() and bounds.width() <= text_box.width():
                chosen, low = size, size + 1
            else:
                high = size - 1
        font.setPixelSize(chosen)
        painter.setFont(font)
        painter.setPen(QColor("#00FF41"))
        painter.drawText(text_box, alignment, text)
        if photo_height:
            size = self.photo.size().scaled(usable.width(), photo_height, Qt.AspectRatioMode.KeepAspectRatio)
            destination = QRect(usable.center().x() - size.width() // 2, usable.bottom() - photo_height + (photo_height - size.height()) // 2, size.width(), size.height())
            painter.drawImage(destination, self.photo)
        font.setPixelSize(13)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#91AD9A"))
        painter.drawText(QRect(margin, self.height() - 37, self.width() - 2 * margin, 24), Qt.AlignmentFlag.AlignCenter, self.footer)

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()


class Overlays(QObject):
    submitted = Signal(str)
    cancelled = Signal()
    display_lost = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.windows = {}
        self.visible = False
        self.authenticating = False
        self.auth_busy = False
        self.auth_detail = ""
        self.message = ""
        self.photo = QImage()
        self.footer = ""
        self.layout_name = ""
        application = QApplication.instance()
        application.screenAdded.connect(self._screens_changed)
        application.screenRemoved.connect(self._screens_changed)
        application.primaryScreenChanged.connect(self._screens_changed)

    def _screens_changed(self, *_args):
        if not QApplication.screens():
            self.display_lost.emit("No display is available. Protection has been stopped.")
            return
        if self.visible:
            self.sync()

    def sync(self):
        screens = QApplication.screens()
        for screen, window in list(self.windows.items()):
            if screen not in screens:
                window.allow_close = True
                window.close()
                del self.windows[screen]
        for screen in screens:
            if screen not in self.windows:
                window = WarningWindow(screen)
                window.panel.submitted.connect(self.submitted)
                window.panel.cancelled.connect(self.cancelled)
                screen.geometryChanged.connect(lambda _geometry, target=screen: self._geometry_changed(target))
                self.windows[screen] = window
            self._update(self.windows[screen], screen == QApplication.primaryScreen())

    def _geometry_changed(self, screen):
        window = self.windows.get(screen)
        if window:
            window.setGeometry(screen.geometry())
            window.place_panel()

    def _update(self, window, primary):
        window.message = self.message
        window.photo = self.photo
        window.footer = self.footer
        should_show = self.authenticating and primary
        if should_show and not window.panel.isVisible():
            window.panel.begin(self.layout_name)
        elif not should_show:
            window.panel.password.clear()
            window.panel.hide()
        if should_show:
            window.panel.layout_label.setText("Keyboard: " + self.layout_name)
            window.panel.set_busy(self.auth_busy, self.auth_detail)
        window.place_panel()
        window.update()

    def show_warning(self, message: str):
        self.message = message
        self.visible = True
        self.sync()

    def show_auth(self, layout_name: str, warning: str):
        self.message = warning
        self.layout_name = layout_name
        self.authenticating = True
        self.auth_busy = False
        self.auth_detail = ""
        self.visible = True
        self.sync()

    def end_auth(self, frozen: bool):
        self.authenticating = False
        self.auth_busy = False
        if frozen:
            self.sync()
        else:
            self.dismiss()

    def set_status(self, remaining, paused=False, requested=False, detail="", busy=False):
        if requested:
            self.footer = "Shutdown requested."
        elif remaining is not None:
            self.footer = f"Shutdown {'paused' if paused else 'in'} · {math.ceil(remaining)} seconds"
        else:
            self.footer = detail if not self.authenticating else ""
        self.auth_busy = busy
        self.auth_detail = detail
        for screen, window in self.windows.items():
            self._update(window, screen == QApplication.primaryScreen())

    def set_photo(self, path: str):
        self.photo = QImage(path)
        for window in self.windows.values():
            window.photo = self.photo
            window.update()

    def handle_key(self, action, text, layout_name):
        self.layout_name = layout_name
        window = self.windows.get(QApplication.primaryScreen())
        if window and window.panel.isVisible():
            window.panel.layout_label.setText("Keyboard: " + layout_name)
            window.panel.handle_key(action, text)

    def dismiss(self):
        self.visible = False
        self.authenticating = False
        for window in self.windows.values():
            window.panel.password.clear()
            window.allow_close = True
            window.close()
        self.windows.clear()
        self.photo = QImage()
        self.footer = ""
