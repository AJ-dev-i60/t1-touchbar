"""Geometry transform: an upright RGB image -> the T1 device frame buffer.

The device's frame buffer is column-major (transposed) and the panel is mounted
with a vertical flip; the per-pixel byte order is plain R,G,B. Verified end-to-end
on a MacBookPro14,3 (2026-06-27). Build the upright image any way you like, then
this turns it into the exact bytes the device expects.
"""
from PIL import Image


def to_device_bytes(img, width, height) -> bytes:
    """Convert an upright image to device-order bytes (length width*height*3).

    `img` may be a PIL Image (any size/mode; it is resized to fit) or raw upright
    width*height*3 RGB bytes.
    """
    if isinstance(img, (bytes, bytearray)):
        if len(img) != width * height * 3:
            raise ValueError(f"raw buffer is {len(img)}, expected {width * height * 3}")
        img = Image.frombytes("RGB", (width, height), bytes(img))
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.size != (width, height):
        img = img.resize((width, height))
    img = img.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.TRANSPOSE)
    return img.tobytes()
