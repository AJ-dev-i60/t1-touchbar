"""t1touchbar_strip — the companion "control strip" app for the t1-touchbar driver.

A reference application built ON TOP of the (thin) `t1touchbar` driver: it shows a
welcome showcase and a default, functional control strip (Esc, brightness, keyboard
backlight, media, volume, and an Fn toggle to the F-keys), so a fresh install lands
on something that visibly works without needing any design tool.

This is intentionally the *opinionated* layer; the core driver stays pure. The layout
is config-driven (see `layout.py`) so it can become user-editable later.

Run it with:  sudo t1touchbar-strip
"""
__version__ = "0.1.0"
