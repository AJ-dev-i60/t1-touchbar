"""Control-strip layouts — a declarative, config-driven button model.

A layout is an ordered list of `Button`s. `action` is a tuple dispatched by
actions.py: ("key", "KEY_ESC"), ("media", "play-pause"), ("volume", "+"|"-"|"mute"),
("brightness", "+"|"-"), ("kbd_backlight", "+"|"-"), ("layout", "<name>").

These are the built-in defaults; a future version loads/merges a user-editable
config file so the strip can be customised without touching code.
"""
from dataclasses import dataclass, field


@dataclass
class Button:
    id: str
    action: tuple
    icon: str = ""          # glyph name in icons.py, or "" to use the text label
    label: str = ""         # text fallback (also used for Esc / F-keys)
    weight: float = 1.0     # relative width


# The default control strip (mirrors the classic Touch Bar control strip).
CONTROL_STRIP = [
    Button("esc", ("key", "KEY_ESC"), label="esc", weight=1.2),
    Button("bright_dn", ("brightness", "-"), icon="bright_dn"),
    Button("bright_up", ("brightness", "+"), icon="bright_up"),
    Button("kbd_dn", ("kbd_backlight", "-"), icon="kbd_dn"),
    Button("kbd_up", ("kbd_backlight", "+"), icon="kbd_up"),
    Button("prev", ("media", "previous"), icon="prev"),
    Button("play", ("media", "play-pause"), icon="play"),
    Button("next", ("media", "next"), icon="next"),
    Button("vol_dn", ("volume", "-"), icon="vol_dn"),
    Button("mute", ("volume", "mute"), icon="mute"),
    Button("vol_up", ("volume", "+"), icon="vol_up"),
    # No Fn softkey: the physical Fn key drives the F-key layout (held -> fkeys).
]

# The F-key layout, shown while the physical Fn key is held.
FKEYS = (
    [Button("esc", ("key", "KEY_ESC"), label="esc", weight=1.2)]
    + [Button(f"f{i}", ("key", f"KEY_F{i}"), label=f"F{i}") for i in range(1, 13)]
)

LAYOUTS = {"control": CONTROL_STRIP, "fkeys": FKEYS}
