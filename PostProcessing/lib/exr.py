"""Minimal reader for the EXR files Unity Perception writes (scanline, ZIP or no compression)."""
import array
import struct
import sys
import zlib

_HALF, _FLOAT = 1, 2
_NO_COMPRESSION, _ZIPS, _ZIP = 0, 2, 3


def read_channel(path, name="R"):
    """One channel of an EXR file as (width, height, list of floats), row by row from the top."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"\x76\x2f\x31\x01":
        raise ValueError(f"{path} is not an EXR")

    header, pos = _read_header(data, 8)
    channels = _channels(header["channels"])
    compression = header["compression"][0]
    x0, y0, x1, y1 = struct.unpack("<iiii", header["dataWindow"])
    width, height = x1 - x0 + 1, y1 - y0 + 1
    lines_per_block = {_NO_COMPRESSION: 1, _ZIPS: 1, _ZIP: 16}.get(compression)
    if lines_per_block is None:
        raise ValueError(f"{path}: unsupported EXR compression {compression}")
    if name not in [c[0] for c in channels]:
        raise ValueError(f"{path}: no channel {name}")

    blocks = (height + lines_per_block - 1) // lines_per_block
    offsets = struct.unpack(f"<{blocks}Q", data[pos:pos + 8 * blocks])
    values = array.array("f", bytes(4 * width * height))

    for offset in offsets:
        y, size = struct.unpack("<ii", data[offset:offset + 8])
        chunk = data[offset + 8:offset + 8 + size]
        lines = min(lines_per_block, y1 - y + 1)
        if compression != _NO_COMPRESSION:
            chunk = _unzip(chunk)
        # Each line holds every channel in turn, channels sorted by name.
        start = 0
        for line in range(lines):
            for channel, kind in channels:
                length = width * (2 if kind == _HALF else 4)
                if channel == name:
                    row = array.array("e" if kind == _HALF else "f", chunk[start:start + length])
                    if sys.byteorder == "big":
                        row.byteswap()
                    first = (y - y0 + line) * width
                    values[first:first + width] = array.array("f", row)
                start += length
    return width, height, values


def _read_header(data, pos):
    header = {}
    while data[pos] != 0:
        end = data.index(b"\0", pos)
        name = data[pos:end].decode()
        end2 = data.index(b"\0", end + 1)
        size = struct.unpack("<i", data[end2 + 1:end2 + 5])[0]
        header[name] = data[end2 + 5:end2 + 5 + size]
        pos = end2 + 5 + size
    return header, pos + 1


def _channels(chlist):
    result, pos = [], 0
    while chlist[pos] != 0:
        end = chlist.index(b"\0", pos)
        kind = struct.unpack("<i", chlist[end + 1:end + 5])[0]
        result.append((chlist[pos:end].decode(), kind))
        pos = end + 17
    return result


def _unzip(chunk):
    raw = zlib.decompress(chunk)
    # Undo the delta predictor, then the split into even and odd bytes.
    raw = bytearray(raw)
    for i in range(1, len(raw)):
        raw[i] = (raw[i - 1] + raw[i] - 128) & 255
    half = (len(raw) + 1) // 2
    out = bytearray(len(raw))
    out[0::2] = raw[:half]
    out[1::2] = raw[half:]
    return bytes(out)
