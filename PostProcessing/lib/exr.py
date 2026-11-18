"""Minimal reader for the EXR files Unity Perception writes (scanline, ZIP or no compression)."""
import struct
import zlib

import numpy as np

_HALF, _FLOAT = 1, 2
_NO_COMPRESSION, _ZIPS, _ZIP = 0, 2, 3


def read_channel(path, name="R"):
    """One channel of an EXR file as a float32 array (height x width), rows from the top."""
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
    names = [c[0] for c in channels]
    if name not in names:
        raise ValueError(f"{path}: no channel {name}")

    # Each line holds every channel in turn (sorted by name), one value per pixel.
    sizes = [2 if kind == _HALF else 4 for _, kind in channels]
    index = names.index(name)
    before = sum(sizes[:index]) * width
    kind = "<f2" if channels[index][1] == _HALF else "<f4"
    line_bytes = sum(sizes) * width

    blocks = (height + lines_per_block - 1) // lines_per_block
    offsets = struct.unpack(f"<{blocks}Q", data[pos:pos + 8 * blocks])
    values = np.empty((height, width), dtype=np.float32)
    for offset in offsets:
        y, size = struct.unpack("<ii", data[offset:offset + 8])
        chunk = data[offset + 8:offset + 8 + size]
        lines = min(lines_per_block, y1 - y + 1)
        if compression != _NO_COMPRESSION:
            chunk = _unzip(chunk)
        rows = np.frombuffer(chunk, dtype=np.uint8, count=lines * line_bytes).reshape(lines, line_bytes)
        part = rows[:, before:before + sizes[index] * width]
        values[y - y0:y - y0 + lines] = np.ascontiguousarray(part).view(kind)
    return values


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
    raw = np.frombuffer(zlib.decompress(chunk), dtype=np.uint8).copy()
    # Undo the delta predictor (running sum minus 128 per byte, wrapping at 256),
    # then the split into even and odd bytes.
    raw[1:] -= 128
    raw = np.cumsum(raw, dtype=np.uint8)
    half = (len(raw) + 1) // 2
    out = np.empty_like(raw)
    out[0::2] = raw[:half]
    out[1::2] = raw[half:]
    return out.tobytes()
