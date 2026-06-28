"""t1bar-studio — a config-driven, themeable, context-aware control surface for the
Apple T1 Touch Bar on Linux, built on the `t1touchbar` driver.

Three layers (see README):
  * config  — JSON describing layouts (widgets), context rules, actions, theme
  * runtime — loads the config, watches context, renders the active layout, routes
              touch to actions, and HOT-RELOADS the config so edits show live on the
              bar in real time
  * editor  — (later) a GUI that writes the config

Run it::

    sudo t1bar run -c configs/default.json
"""
__version__ = "0.1.0"
