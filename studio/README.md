# t1bar-studio — the Scenes customization layer

Design your own **contextual** Touch Bar for the Apple T1 MacBook Pro on Linux. This is the
**optional "Full" path** of [`t1-touchbar`](https://github.com/AJ-dev-i60/t1-touchbar): it draws
custom pixels on the bar (USB **config 2**) and lets you design what lives there. The set-and-forget
**"Basic"** path (the firmware kernel driver, config 1) is owned by the driver side and needs none
of this — see [`../docs/COORDINATION.md`](../docs/COORDINATION.md).

You normally get this by choosing **Full** in the repo-root `./install.sh`; the notes below are for
working on it directly.

## The idea: Scenes

You don't design *a* strip — you define **situations** and what the strip becomes in each. **Scenes**
resolve top-down by priority over an always-on **Always** base; the highest-priority scene whose
**trigger** is currently true is live, and live data updates *inside* a scene without swapping it.
A part's look is a **Layer Loom** (a stack of background / material / icon / effect / motion layers,
any of which can carry a timing envelope); parts **auto-flow** into slots (fixed or stretchy). Every
edit hits the real bar within ~1s.

## Commands

```bash
t1bar scene-edit   -c ~/.config/t1bar/scenes.json   # design it — the native GTK app (Scene Home)
sudo t1bar scene-run -c ~/.config/t1bar/scenes.json # drive the bar (root; hot-reloads on edit)
t1bar scene-render -c scenes.json -o preview.png    # headless preview PNG (no hardware)
t1bar convert -c old-config.json -o scenes.json     # migrate a legacy theme/layouts config
```

The editor writes the live config; the running `t1bar-scenes.service` (`scene-run`) hot-reloads it,
so the bar reflects edits live. `scene-run` is GTK-free; the editor needs **GTK4 + libadwaita +
PyGObject** (`python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi-cairo`; Space Mono optional).

## Config at a glance (`scenes.json`)

```jsonc
{
  "version": 2, "model": "scenes",
  "scenes": [
    { "id": "watching", "name": "Watching", "priority": 2,
      "trigger": { "kind": "media", "state": "playing" },
      "background": [ { "kind": "background", "params": { "type": "solid", "color": [0,0,0] } } ],
      "parts": [
        { "id": "play", "type": "transport", "widthMode": "fixed", "material": "solid",
          "fill": [34,54,44], "action": ["key","KEY_PLAYPAUSE"],
          "layers": [ { "kind": "icon", "params": { "dynamic": "play_pause" } } ] },
        { "id": "seek", "type": "slider", "widthMode": "stretchy",
          "binding": { "source": "media.position" }, "action": ["seek"] }
      ] }
  ],
  "always": { "id": "always", "name": "Always", "priority": 0,
              "trigger": { "kind": "always" }, "parts": [ /* esc · brightness · media · volume */ ] }
}
```

- **Part types:** `key`, `transport`, `slider`, `readout`, `label`, `spacer`.
- **Materials:** `solid` · `frosted` · `outline` · `ghost` · `metal`.
- **Backgrounds:** solid · gradient (motion/texture/image fall back to solid for now).
- **Effects:** glow · shadow · bevel · scanline (ripple is motion-driven, TBD).
- **Motion + envelope:** drift · breathe · flicker · sweep, plus a per-layer `hold·decay·curve`.
- **Triggers:** `always`, `media` (via MPRIS today); `app` / `stat` / `clock` are wired but dark
  until their sources land.

## Status

Engine **Phases 1 & 2 built and hardware-verified** (schema + converter + layered/material
compositor + motion/envelope runtime; 30fps event-driven, ~38fps end-to-end on the real panel).
**Scene Home** GUI built; a **bare-basic editor** (per-part colour / material / width / label,
reorder, add/remove, live-applied) is in. Next: editable icons + key actions, then the deeper Layer
Loom / Auto-flow editing. Design + progress notes live in [`docs/`](docs/).

MIT.
