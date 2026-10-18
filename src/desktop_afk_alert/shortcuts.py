"""Physical key combinations; independent of the privileged runtime."""

from evdev import ecodes

MODIFIER_ALIASES = {
    ecodes.KEY_RIGHTCTRL: ecodes.KEY_LEFTCTRL,
    ecodes.KEY_RIGHTALT: ecodes.KEY_LEFTALT,
    ecodes.KEY_RIGHTSHIFT: ecodes.KEY_LEFTSHIFT,
    ecodes.KEY_RIGHTMETA: ecodes.KEY_LEFTMETA,
}
MODIFIER_LABELS = {
    ecodes.KEY_LEFTCTRL: "Ctrl",
    ecodes.KEY_LEFTALT: "Alt",
    ecodes.KEY_LEFTSHIFT: "Shift",
    ecodes.KEY_LEFTMETA: "Super",
}
DEFAULT_SHORTCUT = [ecodes.KEY_LEFTCTRL, ecodes.KEY_K]
EXCLUDED_KEYS = {ecodes.KEY_POWER, ecodes.KEY_SLEEP, ecodes.KEY_WAKEUP, ecodes.KEY_SUSPEND}


def normalize(code: int) -> int:
    return MODIFIER_ALIASES.get(code, code)


def validate_shortcut(codes: object) -> list[int]:
    if not isinstance(codes, list) or not 1 <= len(codes) <= 3:
        raise ValueError("Record a release shortcut with 1 to 3 simultaneous keys.")
    if any(type(code) is not int or code < 1 or code not in ecodes.KEY for code in codes):
        raise ValueError("Use keyboard keys for the release shortcut.")
    normalized = sorted({normalize(code) for code in codes})
    if len(normalized) != len(codes) or any(code in EXCLUDED_KEYS for code in normalized):
        raise ValueError("Use distinct keyboard keys, excluding power and sleep controls.")
    return normalized


def shortcut_label(codes: list[int]) -> str:
    labels = []
    for code in sorted(codes, key=lambda value: (value not in MODIFIER_LABELS, value)):
        if code in MODIFIER_LABELS:
            labels.append(MODIFIER_LABELS[code])
            continue
        name = ecodes.KEY.get(code, f"KEY_{code}")
        if isinstance(name, (list, tuple)):
            name = name[0]
        label = name.removeprefix("KEY_").replace("_", " ")
        labels.append(label.title() if len(label) > 1 and not label.startswith("F") else label)
    return " + ".join(labels)
