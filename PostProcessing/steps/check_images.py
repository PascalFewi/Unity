"""Save copies of a few frames with all boxes drawn on them, for checking by eye."""
import os

from lib import png

_COLORS = {
    "robot": (255, 40, 40),
    "obstacle": (255, 160, 0),
    "ball": (0, 230, 255),
    "goalpost": (255, 0, 255),
    "L-Intersection": (255, 255, 0),
    "T-Intersection": (0, 255, 0),
    "X-Intersection": (255, 255, 255),
    "PenaltyPoint": (0, 90, 255),
}


def _draw_box(image, box, color):
    x0, y0 = (int(v) for v in box["origin"])
    x1 = min(image.width - 1, x0 + int(box["dimension"][0]))
    y1 = min(image.height - 1, y0 + int(box["dimension"][1]))
    for x in range(x0, x1 + 1):
        _set(image, x, y0, color)
        _set(image, x, y1, color)
    for y in range(y0, y1 + 1):
        _set(image, x0, y, color)
        _set(image, x1, y, color)


def _set(image, x, y, color):
    start = (y * image.width + x) * image.channels
    image.pixels[start:start + 3] = bytes(color)


def process(frame, context):
    limit = context.settings["check_images"]["max_images"]
    step = max(1, context.total_frames // limit)
    if frame.sequence % step != 0:
        return

    image = png.read(frame.image_path)
    for box in frame.boxes:
        _draw_box(image, box, _COLORS.get(box["labelName"], (200, 200, 200)))

    folder = os.path.join(context.out_dir, "check_images")
    os.makedirs(folder, exist_ok=True)
    png.write(os.path.join(folder, f"sequence.{frame.sequence}.png"), image)
