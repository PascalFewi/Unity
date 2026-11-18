"""Read and write 8-bit PNG images as numpy arrays (height x width, or height x width x channels)."""
import numpy as np
from PIL import Image


def read(path):
    with Image.open(path) as image:
        if image.mode == "P":
            image = image.convert("RGBA")
        if image.mode not in ("L", "LA", "RGB", "RGBA"):
            raise ValueError(f"{path}: unsupported PNG mode {image.mode}")
        return np.array(image)


def write(path, pixels):
    Image.fromarray(np.ascontiguousarray(pixels, dtype=np.uint8)).save(path, compress_level=6)
