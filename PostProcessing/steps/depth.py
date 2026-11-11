"""Turn Perception's depth EXR into an 8-bit greyscale PNG for ControlNet depth.

ControlNet depth models are trained on MiDaS-style maps: inverse depth, scaled per image
to 0-255, near = white, far = dark. Pixels where nothing was hit (sky) are black.
"""
import array

from lib import exr, png


def process(frame, context):
    if frame.depth_path is None:
        return
    width, height, depth = exr.read_channel(frame.depth_path, "R")

    inverse = array.array("f", (1.0 / d if d > 0 else 0.0 for d in depth))
    hits = sorted(v for v in inverse if v > 0)
    if not hits:
        pixels = bytearray(width * height)
    else:
        # Scale between percentiles so one object right in front of the camera
        # doesn't push everything else to dark grey. Beyond them the value is clipped.
        clip = context.settings["depth"]["clip_percent"] / 100.0
        low = hits[int(clip * (len(hits) - 1))]
        high = hits[int((1 - clip) * (len(hits) - 1))]
        scale = 254.0 / (high - low) if high > low else 0.0
        # Hits map to 1..255 so only sky is fully black.
        pixels = bytearray(
            0 if v <= 0 else 1 + int(min(254.0, max(0.0, (v - low) * scale)) + 0.5) for v in inverse
        )

    png.write(context.path("depth", frame, ".png"), png.Image(width, height, 1, pixels))
    frame.depth_output = f"depth/{frame.id}.png"
