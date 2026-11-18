"""Save a sample of frames with all boxes drawn on them, for checking by eye."""
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
    height, width = image.shape[:2]
    x0, y0 = (max(0, int(v)) for v in box["origin"])
    x1 = min(width - 1, int(box["origin"][0]) + int(box["dimension"][0]))
    y1 = min(height - 1, int(box["origin"][1]) + int(box["dimension"][1]))
    if x0 > x1 or y0 > y1:
        return
    image[[y0, y1], x0:x1 + 1, :3] = color
    image[y0:y1 + 1, [x0, x1], :3] = color


def process(frame, context):
    if not context.is_check_frame(frame):
        return
    image = png.read(frame.image_path).copy()
    for box in frame.boxes:
        _draw_box(image, box, _COLORS.get(box["labelName"], (200, 200, 200)))
    png.write(context.path("checks/boxes", frame, ".png"), image)
