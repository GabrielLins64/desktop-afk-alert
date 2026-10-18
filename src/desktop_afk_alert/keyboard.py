"""Native XKB keymaps and local password editing, without input reinjection."""

import ast
import ctypes
import ctypes.util
import locale
import mmap
import os
import select
import subprocess
import time

from PySide6.QtDBus import QDBusConnection, QDBusMessage


def library(name: str):
    path = ctypes.util.find_library(name)
    if not path:
        raise RuntimeError(f"Install the system {name} library before activating protection.")
    return ctypes.CDLL(path)


def function(lib, name, arguments, result):
    entry = getattr(lib, name)
    entry.argtypes = arguments
    entry.restype = result
    return entry


class NativeKeyboard:
    def __init__(self, platform: str, seat: str):
        self.lib = library("xkbcommon")
        pointer, number = ctypes.c_void_p, ctypes.c_uint32
        definitions = {
            "xkb_context_new": ([number], pointer),
            "xkb_context_unref": ([pointer], None),
            "xkb_keymap_new_from_string": ([pointer, ctypes.c_char_p, number, number], pointer),
            "xkb_keymap_unref": ([pointer], None),
            "xkb_keymap_num_layouts": ([pointer], number),
            "xkb_keymap_layout_get_name": ([pointer, number], ctypes.c_char_p),
            "xkb_keymap_mod_get_index": ([pointer, ctypes.c_char_p], number),
            "xkb_state_new": ([pointer], pointer),
            "xkb_state_unref": ([pointer], None),
            "xkb_state_update_key": ([pointer, number, number], number),
            "xkb_state_update_mask": ([pointer, number, number, number, number, number, number], number),
            "xkb_state_key_get_one_sym": ([pointer, number], number),
            "xkb_state_key_get_utf8": ([pointer, number, ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int),
            "xkb_state_serialize_layout": ([pointer, number], number),
            "xkb_compose_table_new_from_locale": ([pointer, ctypes.c_char_p, number], pointer),
            "xkb_compose_table_unref": ([pointer], None),
            "xkb_compose_state_new": ([pointer, number], pointer),
            "xkb_compose_state_unref": ([pointer], None),
            "xkb_compose_state_feed": ([pointer, number], number),
            "xkb_compose_state_get_status": ([pointer], number),
            "xkb_compose_state_get_utf8": ([pointer, ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int),
            "xkb_compose_state_reset": ([pointer], None),
        }
        for name, (arguments, result) in definitions.items():
            function(self.lib, name, arguments, result)
        self.context = self.lib.xkb_context_new(0)
        self.keymap = None
        self.state = None
        self.compose_table = None
        self.compose = None
        self.xcb = None
        self.connection = None
        self.wayland = None
        self.wayland_objects = []
        self.group = 0
        self.held = set()
        try:
            if platform == "xcb":
                self._x11()
            elif platform.startswith("wayland"):
                self._wayland(seat)
            else:
                raise RuntimeError("Protection requires a native X11 or Wayland Qt session.")
            if not self.keymap:
                raise RuntimeError("The desktop did not supply a usable keyboard map.")
            self.state = self.lib.xkb_state_new(self.keymap)
            if not self.state:
                raise RuntimeError("Could not initialize the password keyboard layout.")
            selected_locale = (locale.setlocale(locale.LC_CTYPE) or "C.UTF-8").encode()
            self.compose_table = self.lib.xkb_compose_table_new_from_locale(self.context, selected_locale, 0)
            if self.compose_table:
                self.compose = self.lib.xkb_compose_state_new(self.compose_table, 0)
        except BaseException:
            self.close()
            raise

    def _x11(self):
        self.xcb = library("xcb")
        function(self.xcb, "xcb_connect", [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)], ctypes.c_void_p)
        function(self.xcb, "xcb_connection_has_error", [ctypes.c_void_p], ctypes.c_int)
        function(self.xcb, "xcb_disconnect", [ctypes.c_void_p], None)
        self.connection = self.xcb.xcb_connect(None, None)
        if not self.connection or self.xcb.xcb_connection_has_error(self.connection):
            raise RuntimeError("Could not read the X11 keyboard map.")
        native = library("xkbcommon-x11")
        function(native, "xkb_x11_setup_xkb_extension", [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p], ctypes.c_int)
        function(native, "xkb_x11_get_core_keyboard_device_id", [ctypes.c_void_p], ctypes.c_int32)
        function(native, "xkb_x11_keymap_new_from_device", [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int], ctypes.c_void_p)
        function(native, "xkb_x11_state_new_from_device", [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32], ctypes.c_void_p)
        if not native.xkb_x11_setup_xkb_extension(self.connection, 1, 0, 0, None, None, None, None):
            raise RuntimeError("The X server does not provide the XKB extension.")
        device = native.xkb_x11_get_core_keyboard_device_id(self.connection)
        self.keymap = native.xkb_x11_keymap_new_from_device(self.context, self.connection, device, 0)
        if self.keymap:
            state = native.xkb_x11_state_new_from_device(self.keymap, self.connection, device)
            if state:
                self.group = self.lib.xkb_state_serialize_layout(state, 128)
                self.lib.xkb_state_unref(state)

    def _wayland(self, target_seat: str):
        from pywayland.client import Display
        from pywayland.protocol.wayland import WlSeat

        self.wayland = Display()
        self.wayland.connect()
        registry = self.wayland.get_registry()
        self.wayland_objects.append(registry)
        candidates = []

        def global_added(registry_object, name, interface, version):
            if interface != "wl_seat":
                return
            seat = registry_object.bind(name, WlSeat, min(version, 7))
            record = {"seat": seat, "name": "seat0", "keyboard": None}
            candidates.append(record)
            self.wayland_objects.append(seat)

            def seat_name(_seat, value):
                record["name"] = value

            def capabilities(seat_object, flags):
                if flags & 2 and record["keyboard"] is None:
                    keyboard = seat_object.get_keyboard()
                    record["keyboard"] = keyboard
                    self.wayland_objects.append(keyboard)

                    def keymap(_keyboard, format_value, descriptor, size):
                        try:
                            if record["name"] != target_seat or format_value != 1 or not 1 <= size <= 4 * 1024 * 1024:
                                return
                            with mmap.mmap(descriptor, size, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ) as mapping:
                                text = mapping[:].rstrip(b"\0")
                            replacement = self.lib.xkb_keymap_new_from_string(self.context, text, 1, 0)
                            if replacement:
                                if self.keymap:
                                    self.lib.xkb_keymap_unref(self.keymap)
                                self.keymap = replacement
                        finally:
                            os.close(descriptor)

                    keyboard.dispatcher["keymap"] = keymap

            seat.dispatcher["name"] = seat_name
            seat.dispatcher["capabilities"] = capabilities

        registry.dispatcher["global"] = global_added
        for _ in range(4):
            self._roundtrip(2.0)
        if not self.keymap:
            raise RuntimeError("Wayland did not supply the active seat's keyboard map.")
        count = self.lib.xkb_keymap_num_layouts(self.keymap)
        if count > 1:
            self.group = self._wayland_layout(count)

    def _roundtrip(self, timeout: float):
        complete = [False]
        callback = self.wayland.sync()

        def done(callback_object, _serial):
            complete[0] = True
            callback_object.destroy()

        callback.dispatcher["done"] = done
        self.wayland.flush()
        deadline = time.monotonic() + timeout
        while not complete[0]:
            self.wayland.dispatch(block=False)
            if complete[0]:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.wayland.get_fd()], [], [], remaining)[0]:
                raise RuntimeError("Timed out while reading the Wayland keyboard map.")
            self.wayland.read()

    def _wayland_layout(self, count: int) -> int:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "kde" in desktop:
            message = QDBusMessage.createMethodCall("org.kde.keyboard", "/Layouts", "org.kde.KeyboardLayouts", "getLayout")
            reply = QDBusConnection.sessionBus().call(message, timeout=1500)
            if reply.type() != QDBusMessage.MessageType.ErrorMessage and reply.arguments():
                selected = int(reply.arguments()[0])
                if 0 <= selected < count:
                    return selected
        if "gnome" in desktop:
            def sources(key):
                result = subprocess.run(["/usr/bin/gsettings", "get", "org.gnome.desktop.input-sources", key], capture_output=True, timeout=2, check=True)
                text = result.stdout.decode().strip()
                if text.startswith("@a(ss) "):
                    text = text[7:]
                return ast.literal_eval(text)

            try:
                configured = sources("sources")
                recent = sources("mru-sources")
                if recent and recent[0][0] == "xkb":
                    xkb_sources = [source for source in configured if source[0] == "xkb"]
                    selected = xkb_sources.index(recent[0])
                    if 0 <= selected < count and len(xkb_sources) == count:
                        return selected
            except (OSError, ValueError, SyntaxError, subprocess.SubprocessError):
                pass
        raise RuntimeError("Could not identify the active keyboard layout. Select a single XKB keyboard layout in your desktop settings before activating.")

    @property
    def layout_name(self) -> str:
        group = self.lib.xkb_state_serialize_layout(self.state, 128) if self.state else self.group
        name = self.lib.xkb_keymap_layout_get_name(self.keymap, group)
        return name.decode(errors="replace") if name else "System keyboard layout"

    def set_locks(self, caps_lock: bool, num_lock: bool):
        locked = 0
        for name, enabled in ((b"Lock", caps_lock), (b"NumLock", num_lock)):
            index = self.lib.xkb_keymap_mod_get_index(self.keymap, name)
            if enabled and index < 32:
                locked |= 1 << index
        self.lib.xkb_state_update_mask(self.state, 0, 0, locked, 0, 0, self.group)
        self.held.clear()
        self.reset_compose()

    def reset_compose(self):
        if self.compose:
            self.lib.xkb_compose_state_reset(self.compose)

    def translate(self, code: int, value: int, down: bool) -> tuple[str, str]:
        keycode = code + 8
        if value == 0:
            if not down and code in self.held:
                self.held.discard(code)
                self.lib.xkb_state_update_key(self.state, keycode, 0)
            return "", ""
        if value == 1 and code in self.held:
            return "", ""
        symbol = self.lib.xkb_state_key_get_one_sym(self.state, keycode)
        buffer = ctypes.create_string_buffer(128)
        self.lib.xkb_state_key_get_utf8(self.state, keycode, buffer, len(buffer))
        text = buffer.value.decode(errors="replace")
        if value == 1:
            self.held.add(code)
            self.lib.xkb_state_update_key(self.state, keycode, 1)
        actions = {0xFF1B: "cancel", 0xFF0D: "submit", 0xFF8D: "submit", 0xFF08: "backspace", 0xFFFF: "delete", 0xFF51: "left", 0xFF53: "right", 0xFF50: "home", 0xFF57: "end"}
        if symbol in actions:
            composing = self.compose and self.lib.xkb_compose_state_get_status(self.compose) == 1
            self.reset_compose()
            if composing and symbol == 0xFF08:
                return "", ""
            return actions[symbol], ""
        if self.compose:
            self.lib.xkb_compose_state_feed(self.compose, symbol)
            status = self.lib.xkb_compose_state_get_status(self.compose)
            if status == 1:
                return "", ""
            if status == 2:
                self.lib.xkb_compose_state_get_utf8(self.compose, buffer, len(buffer))
                text = buffer.value.decode(errors="replace")
                self.reset_compose()
            elif status == 3:
                self.reset_compose()
                return "", ""
        return "text", "".join(character for character in text if character.isprintable())

    def close(self):
        for attribute, release in (("compose", "xkb_compose_state_unref"), ("compose_table", "xkb_compose_table_unref"), ("state", "xkb_state_unref"), ("keymap", "xkb_keymap_unref"), ("context", "xkb_context_unref")):
            value = getattr(self, attribute, None)
            if value:
                getattr(self.lib, release)(value)
                setattr(self, attribute, None)
        if self.connection:
            self.xcb.xcb_disconnect(self.connection)
            self.connection = None
        if self.wayland:
            self.wayland.disconnect()
            self.wayland = None
