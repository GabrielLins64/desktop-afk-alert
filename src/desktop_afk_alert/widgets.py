"""Accessible switches and a physical, simultaneous-key shortcut recorder."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from desktop_afk_alert.shortcuts import normalize, shortcut_label, validate_shortcut


class Switch(QAbstractButton):
    def __init__(self, label: str, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setAccessibleName(label)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 30)

    def sizeHint(self):
        return QSize(48, 30)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#00D4C7" if self.hasFocus() else "#31543D"), 1))
        painter.setBrush(QColor("#008F11" if self.isChecked() else "#22372A"))
        painter.drawRoundedRect(1, 3, 46, 24, 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#00FF41" if self.isChecked() else "#91AD9A"))
        painter.drawEllipse(26 if self.isChecked() else 5, 7, 16, 16)


class ShortcutRecorder(QDialog):
    def __init__(self, initial: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record release shortcut")
        self.setMinimumWidth(430)
        self.result_keys = initial.copy()
        self.pressed = set()
        self.peak = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(15)
        title = QLabel("Hold 1–3 keys together")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        help_text = QLabel("Release a key to save the combination.\nPower and sleep keys cannot be used.")
        help_text.setObjectName("muted")
        layout.addWidget(help_text)
        self.preview = QLabel(shortcut_label(initial))
        self.preview.setStyleSheet("color: #00FF41; font-size: 24px; padding: 16px 0;")
        layout.addWidget(self.preview)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        event.accept()
        if event.isAutoRepeat():
            return
        code = event.nativeScanCode() - 8
        if code <= 0:
            self.error.setText("The desktop did not provide a physical key code.")
            return
        self.pressed.add(normalize(code))
        if len(self.pressed) >= len(self.peak):
            self.peak = self.pressed.copy()
        self.preview.setText(shortcut_label(sorted(self.peak)))
        if len(self.peak) > 3:
            self.error.setText("Use at most three simultaneous keys. Release all keys and try again.")

    def keyReleaseEvent(self, event):
        event.accept()
        if event.isAutoRepeat():
            return
        self.pressed.discard(normalize(event.nativeScanCode() - 8))
        try:
            selected = validate_shortcut(sorted(self.peak))
        except ValueError as error:
            self.error.setText(str(error))
            if not self.pressed:
                self.peak.clear()
            return
        self.result_keys = selected
        self.accept()
