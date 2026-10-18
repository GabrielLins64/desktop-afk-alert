"""A motion-only virtual pointer; physical buttons and keys are never forwarded."""

import evdev
from evdev import ecodes


class PointerMotion:
    def __init__(self, seat: str):
        if seat != "seat0":
            raise RuntimeError("Cursor movement currently requires seat0. Enable Freeze cursor on other seats.")
        self.sources = {}
        self.enabled = False
        self.output = evdev.UInput(
            {ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y], ecodes.EV_KEY: [ecodes.BTN_LEFT]},
            name="Desktop AFK Alert pointer", phys="desktop-afk-alert/virtual-pointer",
            bustype=ecodes.BUS_VIRTUAL, input_props=[ecodes.INPUT_PROP_POINTER],
        )
        if self.output.device is None:
            self.output.close()
            raise RuntimeError("The virtual pointer could not be identified. Enable Freeze cursor or check uinput access.")
        self.path = self.output.device.path

    def add(self, path: str, device, kind: str):
        if kind not in {"mouse", "touchpad"}:
            return
        absolute = dict(device.capabilities().get(ecodes.EV_ABS, []))
        axes = {}
        for index, (legacy, multitouch) in enumerate(((ecodes.ABS_X, ecodes.ABS_MT_POSITION_X), (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y))):
            code = legacy if legacy in absolute else multitouch
            info = absolute.get(code)
            if info is not None:
                scale = (1000 / 25.4) / info.resolution if info.resolution else 1000 / max(1, info.max - info.min)
                axes[code] = (index, scale)
        self.sources[path] = {"kind": kind, "axes": axes, "slot": 0, "active": kind != "touchpad", "positions": [None, None], "pending": [0.0, 0.0]}

    def remove(self, path: str):
        self.sources.pop(path, None)

    def process(self, path: str, event, enabled: bool):
        if enabled != self.enabled:
            self.enabled = enabled
            for source in self.sources.values():
                source["positions"] = [None, None]
                source["pending"] = [0.0, 0.0]
                source["active"] = source["kind"] != "touchpad"
        source = self.sources.get(path)
        if source is None or not enabled:
            return
        if event.type == ecodes.EV_REL and event.code in (ecodes.REL_X, ecodes.REL_Y):
            source["pending"][0 if event.code == ecodes.REL_X else 1] += event.value
        elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH and source["kind"] == "touchpad":
            source["active"] = bool(event.value)
            source["positions"] = [None, None]
            source["pending"] = [0.0, 0.0]
        elif event.type == ecodes.EV_ABS:
            if event.code == ecodes.ABS_MT_SLOT:
                source["slot"] = event.value
            elif event.code == ecodes.ABS_MT_TRACKING_ID and source["slot"] == 0:
                source["positions"] = [None, None]
            elif event.code in source["axes"] and source["active"]:
                if event.code in (ecodes.ABS_MT_POSITION_X, ecodes.ABS_MT_POSITION_Y) and source["slot"] != 0:
                    return
                axis, scale = source["axes"][event.code]
                previous = source["positions"][axis]
                source["positions"][axis] = event.value
                if previous is not None:
                    source["pending"][axis] += (event.value - previous) * scale
        elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
            moved = False
            for axis, code in enumerate((ecodes.REL_X, ecodes.REL_Y)):
                value = round(source["pending"][axis])
                if value:
                    # BTN_LEFT is advertised for desktop detection, never emitted.
                    self.output.write(ecodes.EV_REL, code, value)
                    source["pending"][axis] -= value
                    moved = True
            if moved:
                self.output.syn()

    def close(self):
        self.sources.clear()
        self.output.close()
