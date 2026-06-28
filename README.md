# t1bar-studio

A **config-driven, themeable, context-aware control surface** for the Apple T1
MacBook Pro Touch Bar on Linux — built on the [`t1-touchbar`](https://github.com/AJ-dev-i60/t1-touchbar)
driver.

Describe what the bar shows, when, and what each control does in a small JSON file.
The runtime renders it on the bar, routes touches to actions, switches layouts based
on context (e.g. media playing), and **hot-reloads the config so your edits appear on
the bar live** — change a button's colour and watch it update in real time.

## Run

```bash
sudo t1bar run -c configs/default.json     # drive the bar; edits reload live
```

Preview a layout without the hardware (writes a PNG):

```bash
t1bar render -c configs/default.json -l media --playing -o preview.png
```

## Config at a glance

```jsonc
{
  "theme": {                      // global defaults; every field is optional
    "background": [8,10,18],
    "button": { "fill": [38,42,58], "text": [232,234,240], "radius": 12, "font_size": 26 },
    "pressed": { "fill": [70,110,210] },
    "accent": [90,170,250]        // scrubber fill
  },
  "layouts": {
    "default": { "items": [
      { "type":"button", "id":"esc", "label":"esc", "action":["key","KEY_ESC"],
        "fill":[60,40,48] },                       // per-button colour override
      { "type":"button", "id":"play", "icon":"play", "dynamic":"play_pause",
        "action":["key","KEY_PLAYPAUSE"] },
      { "type":"spacer", "weight":0.4 }
    ] },
    "media": { "items": [
      { "type":"label", "source":"media_title", "weight":2 },
      { "type":"scrubber", "source":"media_position", "action":["seek"], "weight":5 }
    ] }
  },
  "rules": [                       // first match wins; no "when" = default
    { "when": { "media":"playing" }, "show":"media" },
    { "show":"default" }
  ]
}
```

**Items** lay out left→right, widths split by `weight`. Types: `button` (label or
`icon`, with `fill`/`color` overrides and `dynamic:"play_pause"`), `scrubber`
(`source:"media_position"`, tap to seek), `label` (static or `source:"media_title"`),
`spacer`.

**Actions:** `["key","KEY_*"]` (emits a key; the desktop shows its native OSD),
`["media","play-pause"]`, `["seek", <0..1>]`, `["command", ...]`, `["layout","name"]`.

**Context:** Stage 1 ships MPRIS media (covers Spotify and browser video). Focused-app
and system-stat sources are next.

## Status

Stage 1: config model + runtime + themeable widgets + live hot-reload. The GUI editor
and an app-SDK (per-app context like a YouTube scrubber) are on the roadmap.

MIT.
