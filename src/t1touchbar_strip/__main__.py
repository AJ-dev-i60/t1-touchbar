"""Entry point: `t1touchbar-strip [options]`.

    t1touchbar-strip                welcome showcase, then the control strip
    t1touchbar-strip --no-welcome   skip the welcome showcase
    t1touchbar-strip --welcome-once play the welcome only on first ever run
    t1touchbar-strip --welcome-only play only the welcome showcase and exit
    t1touchbar-strip --dry-run      log actions instead of applying them
"""
import os
import sys

WELCOME_MARKER = "/var/lib/t1touchbar/welcomed"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--welcome-only" in argv:
        from t1touchbar import Device
        from . import welcome
        with Device() as bar:
            welcome.play(bar.blit, bar.width, bar.height)
        return 0

    show_welcome = "--no-welcome" not in argv
    if "--welcome-once" in argv:
        # Play the welcome only the first time (e.g. on first boot after install).
        show_welcome = not os.path.exists(WELCOME_MARKER)
        if show_welcome:
            try:
                os.makedirs(os.path.dirname(WELCOME_MARKER), exist_ok=True)
                open(WELCOME_MARKER, "a").close()
            except OSError:
                pass

    from .app import StripApp
    on_action = None
    if "--dry-run" not in argv:
        from . import actions
        on_action = actions.dispatch
    StripApp(show_welcome=show_welcome, on_action=on_action).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
