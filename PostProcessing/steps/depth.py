"""Turn Perception's depth EXR into an 8-bit greyscale PNG for ControlNet depth.

ControlNet depth models are trained on MiDaS-style maps: inverse depth, scaled per image
to 0-255, near = white, far = dark. Pixels where nothing was hit (sky) are black.
"""
import numpy as np

from lib import png


def process(frame, context):
    depth = frame.depth()
    if depth is None:
        return

    hit = depth > 0
    inverse = np.zeros(depth.shape, dtype=np.float32)
    inverse[hit] = 1.0 / depth[hit].astype(np.float64)
    pixels = np.zeros(depth.shape, dtype=np.uint8)
    hits = np.sort(inverse[hit]).astype(np.float64)
    if len(hits):
        # Scale between percentiles so one object right in front of the camera
        # doesn't push everything else to dark grey. Beyond them the value is clipped.
        clip = context.settings["depth"]["clip_percent"] / 100.0
        low = hits[int(clip * (len(hits) - 1))]
        high = hits[int((1 - clip) * (len(hits) - 1))]
        scale = 254.0 / (high - low) if high > low else 0.0
        # Hits map to 1..255 so only sky is fully black.
        scaled = np.clip((inverse[hit].astype(np.float64) - low) * scale, 0.0, 254.0)
        pixels[hit] = 1 + np.floor(scaled + 0.5).astype(np.uint8)

    png.write(context.path("depth", frame, ".png"), pixels)
    frame.depth_output = f"depth/{frame.id}.png"
