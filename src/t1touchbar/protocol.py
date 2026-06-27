"""DFR display-protocol framing for the Apple T1 (iBridge) Touch Bar.

Pure functions, no USB or I/O. This is the wire format the device speaks on its
config-2 Audio/Video interface. See docs/PROTOCOL.md and docs/DEVGUIDE.md for how
it was reverse-engineered. All multi-byte fields are little-endian.
"""
import struct

# Message magics (ASCII tags, little-endian on the wire).
GINF = 0x47494E46  # GET_INFORMATION  (host->device: query panel geometry)
REDY = 0x52454459  # SIGNAL_READINESS (host->device)
CLRD = 0x434C5244  # CLEAR_DISPLAY    (host->device)
UDCL = 0x5544434C  # UPDATE_COMPLETE  (device->host: a frame finished rendering)


def tag(resp: bytes) -> str:
    """ASCII message tag at byte offset 16 of a device response (or '?')."""
    return resp[16:20][::-1].decode("ascii", "replace") if len(resp) >= 20 else "?"


def simple_request(msg: int) -> bytes:
    """A 32-byte control request (GINF / REDY / CLRD).

    The two size fields are 16 (= sizeof(struct) - sizeof(16-byte header)); a
    value of 20 makes the device reject the command.
    """
    header = struct.pack("<HHIII", 2, 0x1512, 0, 0, 16)
    return header + struct.pack("<I", msg) + b"\x00" * 8 + struct.pack("<I", 16)


def parse_information(buf: bytes):
    """Parse a GINF (information) response into a dict, or None if too short."""
    if len(buf) < 57:
        return None
    return dict(
        msg=struct.unpack_from("<I", buf, 16)[0],
        width=struct.unpack_from("<I", buf, 32)[0],
        height=struct.unpack_from("<I", buf, 36)[0],
        bpp=buf[40],
        bytes_per_row=struct.unpack_from("<I", buf, 41)[0],
        pixel_format=struct.unpack_from("<I", buf, 53)[0],
    )


def fb_request(width: int, height: int, buf: bytes, timestamp: int) -> bytes:
    """Build a full-panel framebuffer-update request.

    `buf` must be width*height*3 bytes already in the DEVICE byte order (use
    geometry.to_device_bytes to produce it from an upright image). `timestamp` is
    any nonzero 64-bit value; the device echoes it in the UDCL ack.
    """
    if len(buf) != width * height * 3:
        raise ValueError(f"buf is {len(buf)} bytes, expected {width * height * 3}")
    frame = struct.pack("<HHHHI", 0, 0, width, height, len(buf)) + buf
    footer = bytearray(80)
    struct.pack_into("<I", footer, 12, 0xFFFE)
    struct.pack_into("<I", footer, 28, 0x80001)
    struct.pack_into("<Q", footer, 32, timestamp)
    struct.pack_into("<I", footer, 52, 0x80002)
    struct.pack_into("<I", footer, 76, 0xFFFF)
    data = frame + bytes(footer)
    request_size = 48 + len(data)
    hdr = struct.pack("<HHIII", 2, 0x12, 9, 0, request_size - 16)
    pre = struct.pack("<HB", 1, timestamp & 0xFF) + b"\x00" * 29
    return hdr + pre + data
