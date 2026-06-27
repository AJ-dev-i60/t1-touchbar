# Protocols

Two layers are documented here: the **socket API** your tools talk to (stable contract),
and a summary of the **DFR wire protocol** the driver speaks to the hardware. The full
wire-level reverse-engineering reference is in [`DEVGUIDE.md`](DEVGUIDE.md).

---

## 1. Socket API (`t1touchbar serve`)

A `SOCK_STREAM` Unix socket (default `/tmp/t1touchbar.sock`). Every message, both
directions, is framed as:

```
[ 4 bytes: payload length, big-endian uint32 ][ 1 byte: type ][ payload ]
```

### Client → server

| Type | Name  | Payload | Effect |
|------|-------|---------|--------|
| `0x01` | `FRAME` | `width*height*3` bytes, upright RGB (row-major) | display this framebuffer |
| `0x02` | `IMG`   | encoded image bytes (PNG/JPG/…) | decode, resize to panel, display |
| `0x03` | `CLEAR` | — | blank the panel |
| `0x04` | `INFO`  | — | request panel info (server replies `INFO`) |
| `0x05` | `PING`  | — | server replies `PONG` |

`FRAME` is the fast path (no decode). Send an upright `2170×60` RGB buffer; the driver
applies the geometry transform and synchronous pacing. The bar sustains ~90 fps.

### Server → client

| Type | Name  | Payload |
|------|-------|---------|
| `0x81` | `TOUCH` | JSON `{"x": int, "y": int, "state": "down"\|"move"\|"up"}` |
| `0x82` | `INFO`  | JSON `{"width": 2170, "height": 60, "bpp": 24, ...}` |
| `0x83` | `PONG`  | — |

`TOUCH` events are broadcast to all connected clients. `x` is `0..width` (left→right),
`y` is `0..height` (top→bottom).

### Minimal client (pseudocode)

```
connect("/tmp/t1touchbar.sock")
send( u32be(len(rgb)) + 0x01 + rgb )          # display a frame
loop:
    length, type = read(4) , read(1)
    payload = read(length)
    if type == 0x81: handle_touch(json(payload))
```

A reference Python client ships as `t1touchbar.client.Client`.

---

## 2. DFR wire protocol (driver ↔ device) — summary

The Touch Bar lives on USB `05ac:8600`, **configuration 2**, the **Audio/Video (class
16)** interface, endpoints **Bulk OUT `0x02`** / **Bulk IN `0x85`**. Messages are
little-endian.

- **Control messages** are a 32-byte "simple request": header `{u16 2, u16 0x1512, u32 0,
  u32 0, u32 16}` + `u32 msg` + 8 zero bytes + `u32 16`. Magics: `GINF` (get info),
  `REDY` (signal readiness), `CLRD` (clear), `UDCL` (update complete).
- **Handshake:** send `GINF`, read the 65-byte info reply (width@32, height@36, bpp@40,
  pixel_format@53; panel = **2170×60, 24bpp**), then send `REDY`.
- **Frames:** a header `{u16 2, u16 0x12, u32 9, u32 0, u32 size}` + `{u16 1, u8 msg_id,
  29 zero}` + one `frame{u16 begin_x, begin_y, width, height; u32 buf_size; buf[]}` +
  an 80-byte footer (`0xfffe@12`, `0x80001@28`, `u64 timestamp@32`, `0x80002@52`,
  `0xffff@76`). Pixels are **BGR/RGB 24-bit** in a **transposed, vertically-flipped**
  layout (see `geometry.to_device_bytes`).
- **Pacing is synchronous:** after each frame, read until the device sends `UDCL` before
  sending the next. Skipping this drops frames *and* stalls the device.

Touch is read separately from the kernel-exposed evdev device **"Apple Inc. iBridge
Touchpad"**: `ABS_X` 0..32767, `ABS_Y` 0..127, `BTN_TOUCH`. Map with
`pixel_x = ABS_X / ABS_X.max * width` (linear, not flipped).

Full byte-level detail, the discovery story, and performance numbers: [`DEVGUIDE.md`](DEVGUIDE.md).
