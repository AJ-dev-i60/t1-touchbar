"""Entry point: `t1touchbar-strip [options]`.

    t1touchbar-strip                run the welcome showcase then the control strip
    t1touchbar-strip --no-welcome   skip the welcome showcase
    t1touchbar-strip --welcome-only play only the welcome showcase and exit
"""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--welcome-only" in argv:
        from t1touchbar import Device
        from . import welcome
        with Device() as bar:
            welcome.play(bar.blit, bar.width, bar.height)
        return 0

    from .app import StripApp
    StripApp(show_welcome="--no-welcome" not in argv).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
