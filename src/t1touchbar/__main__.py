"""Command-line entry point: `t1touchbar <command>`.

    t1touchbar serve            run the socket daemon (owns the device)
    t1touchbar info             print panel geometry (needs a running daemon)
    t1touchbar send <image>     display an image file (needs a running daemon)
    t1touchbar clear            blank the bar (needs a running daemon)
    t1touchbar version
"""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "help"

    if cmd == "serve":
        from .server import Server
        Server().serve()

    elif cmd == "info":
        from .client import Client
        print(Client().info())

    elif cmd == "send" and len(argv) > 1:
        from .client import Client
        Client().image(argv[1])

    elif cmd == "clear":
        from .client import Client
        Client().clear()

    elif cmd in ("version", "--version", "-V"):
        from . import __version__
        print(f"t1touchbar {__version__}")

    else:
        print(__doc__.strip())
        return 0 if cmd in ("help", "-h", "--help") else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
