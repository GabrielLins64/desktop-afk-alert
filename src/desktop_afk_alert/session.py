"""Desktop session discovery and a scoped idle/suspend inhibitor."""

import os
import re
import subprocess
import threading
import uuid

from PySide6.QtCore import QObject, Signal


def current_session() -> tuple[str, str, str]:
    identifier = os.environ.get("XDG_SESSION_ID", "auto")
    if identifier != "auto" and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
        raise RuntimeError("Invalid desktop session identifier.")
    try:
        result = subprocess.run(
            ["/usr/bin/loginctl", "show-session", identifier, "--no-pager", "-p", "Id", "-p", "User", "-p", "Active", "-p", "Remote", "-p", "Type", "-p", "Seat", "-p", "LockedHint"],
            capture_output=True, timeout=3, check=True,
        )
        properties = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
        if properties.get("User") != str(os.getuid()) or properties.get("Active") != "yes" or properties.get("Remote") != "no" or properties.get("Type") not in {"x11", "wayland"} or properties.get("LockedHint") == "yes" or not properties.get("Seat"):
            raise ValueError
        return properties["Id"], properties["Seat"], properties["Type"]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise RuntimeError("Start the application in your active, unlocked local X11 or Wayland desktop session.") from None


class SessionInhibitor(QObject):
    lost = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.handle = ""
        self.stop_event = None

    def acquire(self):
        if self.handle:
            return
        stop = threading.Event()
        ready = threading.Event()
        result = {}
        self.stop_event = stop
        threading.Thread(target=self._serve, args=(stop, ready, result), daemon=True).start()
        if not ready.wait(5) or "error" in result:
            stop.set()
            self.stop_event = None
            raise RuntimeError("Idle and suspend inhibition is unavailable. Install and start the desktop portal for GNOME or KDE.")
        self.handle = result["handle"]

    def _serve(self, stop, ready, result):
        from jeepney import DBusAddress, HeaderFields, MatchRule, MessageType, new_method_call
        from jeepney.io.blocking import open_dbus_connection

        connection = None
        handle = ""
        try:
            connection = open_dbus_connection(auth_timeout=1)
            with connection.filter(MatchRule(type="signal"), bufsize=32) as signals:
                bus = DBusAddress("/org/freedesktop/DBus", bus_name="org.freedesktop.DBus", interface="org.freedesktop.DBus")
                rule = "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.freedesktop.portal.Desktop'"
                connection.send_and_get_reply(new_method_call(bus, "AddMatch", "s", (rule,)), timeout=1)
                portal = DBusAddress("/org/freedesktop/portal/desktop", bus_name="org.freedesktop.portal.Desktop", interface="org.freedesktop.portal.Inhibit")
                options = {"handle_token": ("s", "afk_" + uuid.uuid4().hex), "reason": ("s", "Desktop AFK Alert is monitoring this desktop.")}
                reply = connection.send_and_get_reply(new_method_call(portal, "Inhibit", "sua{sv}", ("", 12, options)), timeout=2)
                if reply.header.message_type == MessageType.error or not reply.body:
                    raise RuntimeError("Inhibition was rejected.")
                handle = reply.body[0]
                if not handle.startswith("/org/freedesktop/portal/desktop/request/"):
                    raise RuntimeError("Invalid inhibitor handle.")
                result["handle"] = handle
                ready.set()
                while not stop.is_set():
                    while signals:
                        message = signals.popleft()
                        fields = message.header.fields
                        if fields.get(HeaderFields.member) == "Response" and fields.get(HeaderFields.path) == handle and message.body[0] != 0:
                            raise RuntimeError("The desktop rejected idle and suspend inhibition.")
                        if fields.get(HeaderFields.member) == "NameOwnerChanged" and message.body[0] == "org.freedesktop.portal.Desktop" and not message.body[2]:
                            raise RuntimeError("The desktop portal stopped. Protection has been stopped.")
                    try:
                        connection.recv_messages(timeout=0.2)
                    except TimeoutError:
                        pass
        except Exception:
            result["error"] = True
            if ready.is_set() and not stop.is_set():
                self.lost.emit("Desktop session inhibition was lost. Protection has been stopped.")
            ready.set()
        finally:
            if connection:
                if handle:
                    try:
                        address = DBusAddress(handle, bus_name="org.freedesktop.portal.Desktop", interface="org.freedesktop.portal.Request")
                        connection.send(new_method_call(address, "Close"))
                    except Exception:
                        pass
                connection.close()

    def release(self):
        self.handle = ""
        if self.stop_event:
            self.stop_event.set()
            self.stop_event = None
