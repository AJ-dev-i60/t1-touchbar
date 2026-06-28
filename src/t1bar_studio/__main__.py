"""t1bar — run or preview a config-driven Touch Bar control surface.

    sudo t1bar run -c configs/default.json     drive the bar (live hot-reload)
    t1bar render -c configs/default.json -l media -o out.png   headless preview PNG
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

    e = sub.add_parser("edit", help="open the native GTK editor (live-edits the config)")
    e.add_argument("-c", "--config", required=True)
    e.add_argument("--shot", help=argparse.SUPPRESS)   # render UI to PNG and exit

    args = ap.parse_args(argv)

    if args.cmd == "edit":
        if not os.path.exists(args.config):
            ap.error(f"config not found: {args.config}")
        from .editor_gtk import run
        run(args.config, shot=getattr(args, "shot", None))
        return 0

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


if __name__ == "__main__":
    sys.exit(main())
