"""Minimal 8-bit PNG reader and writer, standard library only."""
import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


class Image:
    """Pixels stored row by row, `channels` bytes per pixel."""

    def __init__(self, width, height, channels, pixels):
        self.width = width
        self.height = height
        self.channels = channels
        self.pixels = pixels

    def pixel(self, x, y):
        start = (y * self.width + x) * self.channels
        return tuple(self.pixels[start:start + self.channels])


def read(path):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(_SIGNATURE):
        raise ValueError(f"{path} is not a PNG")

    pos = len(_SIGNATURE)
    compressed = bytearray()
    width = height = channels = None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or color not in _CHANNELS or interlace:
                raise ValueError(f"{path}: unsupported PNG (depth {depth}, color {color}, interlace {interlace})")
            channels = _CHANNELS[color]
        elif kind == b"IDAT":
            compressed += chunk
        elif kind == b"IEND":
            break

    raw = zlib.decompress(bytes(compressed))
    return Image(width, height, channels, _unfilter(raw, width, height, channels))


def _unfilter(raw, width, height, bpp):
    stride = width * bpp
    out = bytearray(stride * height)
    previous = bytearray(stride)
    pos = 0
    for y in range(height):
        kind = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if kind == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif kind == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, previous))
        elif kind == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + (left + previous[i]) // 2) & 255
        elif kind == 4:
            for i in range(stride):
                a = row[i - bpp] if i >= bpp else 0
                b = previous[i]
                c = previous[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                best = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + best) & 255
        elif kind != 0:
            raise ValueError(f"unknown PNG filter {kind}")
        out[y * stride:(y + 1) * stride] = row
        previous = row
    return out


def write(path, image):
    color = {v: k for k, v in _CHANNELS.items()}[image.channels]
    stride = image.width * image.channels
    raw = bytearray()
    for y in range(image.height):
        raw.append(0)
        raw += image.pixels[y * stride:(y + 1) * stride]

    def chunk(kind, body):
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", image.width, image.height, 8, color, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(_SIGNATURE)
        f.write(chunk(b"IHDR", header))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(chunk(b"IEND", b""))
