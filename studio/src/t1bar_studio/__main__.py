"""t1bar — design and drive a contextual Touch Bar control surface.

  Scenes engine (current):
    t1bar scene-edit -c ~/.config/t1bar/scenes.json     design it (native GTK app)
    sudo t1bar scene-run -c ~/.config/t1bar/scenes.json drive the bar (hot-reload)
    t1bar scene-render -c scenes.json -o out.png        headless preview PNG
    t1bar convert -c config.json -o scenes.json          legacy config -> scenes
  Legacy engine (fallback, kept for switch-engine.sh legacy):
    sudo t1bar run -c config.json   ·   t1bar render -c config.json -o out.png
"""
import argparse
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="t1bar")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="drive the Touch Bar from a config (hot-reload)")
    r.add_argument("-c", "--config", required=True)

    p = sub.add_parser("render", help="render a layout to a PNG (no hardware)")
    p.add_argument("-c", "--config", required=True)
    p.add_argument("-l", "--layout", default=None, help="layout name (default: first)")
    p.add_argument("-o", "--out", default="t1bar-preview.png")
    p.add_argument("--width", type=int, default=2170)
    p.add_argument("--height", type=int, default=60)
    p.add_argument("--playing", action="store_true", help="fake media-playing state")

    # ── new Scenes engine ────────────────────────────────────────────────────
    cv = sub.add_parser("convert", help="convert a legacy config into a Scenes config")
    cv.add_argument("-c", "--config", required=True, help="legacy config (in)")
    cv.add_argument("-o", "--out", required=True, help="scenes config (out)")

    rn = sub.add_parser("scene-run",
                        help="drive the Touch Bar from a Scenes config (new runtime, hot-reload)")
    rn.add_argument("-c", "--config", required=True)

    se = sub.add_parser("scene-edit",
                        help="open Scene Home — the native GTK Scenes app")
    se.add_argument("-c", "--config", required=True)
    se.add_argument("--shot", help=argparse.SUPPRESS)   # render UI to PNG and exit

    sr = sub.add_parser("scene-render",
                        help="render a Scenes config to a PNG (new compositor, no hardware)")
    sr.add_argument("-c", "--config", required=True, help="a Scenes config")
    sr.add_argument("-s", "--scene", default=None,
                    help="scene id to render (default: the active scene for the state)")
    sr.add_argument("-o", "--out", default="t1bar-scene.png")
    sr.add_argument("--playing", action="store_true", help="fake media-playing state")
    sr.add_argument("--frac", type=float, default=0.4, help="fake slider fraction 0..1")
    sr.add_argument("-t", "--time", type=float, default=0.0, help="motion time (seconds)")

    args = ap.parse_args(argv)

    if args.cmd == "run":
        if os.geteuid() != 0:
            ap.error("run must be root (USB + uinput)")
        from .runtime import Runtime
        Runtime(args.config).run()
        return 0

    if args.cmd == "render":
        from . import config as cfgmod, render
        cfg = cfgmod.load(args.config)
        layout = args.layout or next(iter(cfg["layouts"]), None)
        if layout not in cfg["layouts"]:
            ap.error(f"no such layout: {layout} (have {list(cfg['layouts'])})")
        media = {"status": "Playing" if args.playing else "Stopped",
                 "position": 73.0, "length": 210.0, "title": "Demo Track"}
        state = {"width": args.width, "height": args.height, "pressed": None,
                 "media": media}
        render.render(cfg, layout, state).save(args.out)
        print(f"wrote {args.out} ({layout})")
        return 0

    if args.cmd == "scene-run":
        if os.geteuid() != 0:
            ap.error("scene-run must be root (USB + uinput)")
        from .scene_runtime import SceneRuntime
        SceneRuntime(args.config).run()
        return 0

    if args.cmd == "scene-edit":
        if not os.path.exists(args.config):
            ap.error(f"config not found: {args.config}")
        from .scene_app import run as run_app
        run_app(args.config, shot=getattr(args, "shot", None))
        return 0

    if args.cmd == "convert":
        from . import convert, model
        cfg = convert.convert_file(args.config)
        model.save(cfg, args.out)
        names = [f"{s.name}(p{s.priority})" for s in cfg.all_scenes()]
        print(f"wrote {args.out} — scenes: {', '.join(names)}")
        return 0

    if args.cmd == "scene-render":
        from . import compose, model, scenes
        cfg = model.load(args.config)
        media = {"status": "Playing" if args.playing else "Stopped",
                 "position": 73.0, "length": 210.0,
                 "title": "Demo Track", "artist": "Some Artist"}
        live = {"media": media, "frac": args.frac, "cpu": 38, "gpu": 71,
                "app": "mpv" if args.playing else "", "clock": "12:40"}
        if args.scene:
            scene = cfg.scene_by_id(args.scene)
            if scene is None:
                ap.error(f"no such scene: {args.scene} "
                         f"(have {[s.id for s in cfg.all_scenes()]})")
            why = "explicitly selected"
        else:
            scene, why = scenes.resolve_with_reason(cfg, live)
        compose.compose(cfg, live, scene=scene, t=args.time).save(args.out)
        print(f"wrote {args.out} — scene '{scene.name}' (because {why})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
