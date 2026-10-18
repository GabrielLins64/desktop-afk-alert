"""Exclusive seat-local input capture. This module is imported by the helper only."""

import selectors
import time

import evdev
import pyudev
from evdev import ecodes


class InputCapture:
    def __init__(self, selector: selectors.BaseSelector, seat: str):
        self.selector = selector
        self.seat = seat
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem="input")
        self.monitor.start()
        self.selector.register(self.monitor.fileno(), selectors.EVENT_READ, ("udev", None))
        self.devices: dict[str, evdev.InputDevice] = {}
        self.pressed: dict[str, set[int]] = {}
        self.kinds = {}
        self.positions = {}
        self.taps = {}
        self.tap_thresholds = {}
        self.removed_keys = set()
        self.active = False

    def eligible(self, device: pyudev.Device) -> bool:
        if not device.device_node or not device.device_node.startswith("/dev/input/event"):
            return False
        if device.properties.get("ID_SEAT", "seat0") != self.seat:
            return False
        if device.properties.get("ID_INPUT_JOYSTICK") == "1" and device.properties.get("ID_INPUT_KEYBOARD") != "1" and device.properties.get("ID_INPUT_MOUSE") != "1":
            return False
        tags = ("ID_INPUT_KEYBOARD", "ID_INPUT_KEY", "ID_INPUT_MOUSE", "ID_INPUT_TOUCHPAD", "ID_INPUT_TOUCHSCREEN")
        return any(device.properties.get(tag) == "1" for tag in tags)

    def _add(self, device: pyudev.Device) -> None:
        path = device.device_node
        if path in self.devices or not self.eligible(device):
            return
        handle = evdev.InputDevice(path)
        try:
            if handle.active_keys():
                raise BlockingIOError("Release all keys and buttons to arm.")
            handle.grab()
            if handle.active_keys():
                raise BlockingIOError("Release all keys and buttons to arm.")
            self.selector.register(handle.fd, selectors.EVENT_READ, ("input", path))
            self.devices[path] = handle
            self.pressed[path] = set()
            self.kinds[path] = "touchpad" if device.properties.get("ID_INPUT_TOUCHPAD") == "1" else "touchscreen" if device.properties.get("ID_INPUT_TOUCHSCREEN") == "1" else "mouse" if device.properties.get("ID_INPUT_MOUSE") == "1" else "other"
            self.positions[path] = [None, None]
            thresholds = []
            absolute = dict(handle.capabilities().get(ecodes.EV_ABS, []))
            for axis in (ecodes.ABS_X, ecodes.ABS_Y):
                alternative = ecodes.ABS_MT_POSITION_X if axis == ecodes.ABS_X else ecodes.ABS_MT_POSITION_Y
                info = absolute.get(axis) or absolute.get(alternative)
                thresholds.append(max(10, info.resolution * 3 if info and info.resolution else (info.max - info.min) * 0.02 if info else 10))
            self.tap_thresholds[path] = thresholds
        except OSError as error:
            handle.close()
            if isinstance(error, BlockingIOError):
                raise
            raise RuntimeError("Cannot capture an input device. Close keyboard/mouse remappers and check system input-access policies.") from None
        except BaseException:
            handle.close()
            raise

    def grab(self) -> bool:
        self.release()
        candidates = [device for device in self.context.list_devices(subsystem="input") if self.eligible(device)]
        if not any(device.properties.get("ID_INPUT_KEYBOARD") == "1" for device in candidates):
            raise RuntimeError("No keyboard was found on the active seat.")
        try:
            for device in candidates:
                self._add(device)
        except BlockingIOError:
            self.release()
            return False
        except BaseException:
            self.release()
            raise
        self.active = True
        return True

    def hotplug(self) -> None:
        while True:
            device = self.monitor.poll(timeout=0)
            if device is None:
                return
            path = device.device_node
            if device.action == "remove" and path in self.devices:
                self.remove(path)
            elif self.active and device.action in ("add", "change") and self.eligible(device):
                self._add(device)

    def remove(self, path: str) -> None:
        previously_held = self.held() if self.active else set()
        handle = self.devices.pop(path, None)
        self.pressed.pop(path, None)
        self.kinds.pop(path, None)
        self.positions.pop(path, None)
        self.taps.pop(path, None)
        self.tap_thresholds.pop(path, None)
        self.removed_keys.update(previously_held - self.held())
        if handle is not None:
            try:
                self.selector.unregister(handle.fd)
            except (KeyError, ValueError):
                pass
            handle.close()

    def take_removed_keys(self) -> set[int]:
        released, self.removed_keys = self.removed_keys, set()
        return released

    def read(self, path: str):
        device = self.devices.get(path)
        if device is None:
            return []
        try:
            return list(device.read())
        except BlockingIOError:
            return []
        except OSError:
            self.remove(path)
            return []

    def held(self) -> set[int]:
        return set().union(*self.pressed.values()) if self.pressed else set()

    def update(self, path: str, code: int, value: int) -> None:
        keys = self.pressed.get(path)
        if keys is None:
            return
        if value == 1:
            keys.add(code)
        elif value == 0:
            keys.discard(code)

    def pointer_click(self, path: str, event) -> bool:
        kind = self.kinds.get(path)
        if event.type == ecodes.EV_ABS and kind == "touchpad":
            axes = {ecodes.ABS_X: 0, ecodes.ABS_Y: 1, ecodes.ABS_MT_POSITION_X: 0, ecodes.ABS_MT_POSITION_Y: 1}
            axis = axes.get(event.code)
            if axis is not None:
                self.positions[path][axis] = event.value
                tap = self.taps.get(path)
                if tap:
                    if tap["origin"][axis] is None:
                        tap["origin"][axis] = event.value
                    elif abs(event.value - tap["origin"][axis]) > self.tap_thresholds[path][axis]:
                        tap["moved"] = True
            return False
        if event.type != ecodes.EV_KEY:
            return False
        if ecodes.BTN_MOUSE <= event.code < ecodes.BTN_JOYSTICK and event.value == 1:
            return True
        if kind == "mouse" and ecodes.BTN_MISC <= event.code < ecodes.BTN_MOUSE and event.value == 1:
            return True
        if event.code == ecodes.BTN_TOUCH:
            if kind == "touchscreen":
                return event.value == 1
            if kind == "touchpad":
                if event.value == 1:
                    self.taps[path] = {"time": time.monotonic(), "origin": self.positions[path].copy(), "moved": False}
                elif event.value == 0:
                    tap = self.taps.pop(path, None)
                    return bool(tap and not tap["moved"] and time.monotonic() - tap["time"] <= 0.25)
        return False

    def release(self) -> None:
        self.active = False
        for path in list(self.devices):
            self.remove(path)

    def close(self) -> None:
        self.release()
        try:
            self.selector.unregister(self.monitor.fileno())
        except (KeyError, ValueError):
            pass
