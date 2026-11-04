"""Replace Perception's crossing boxes with boxes calculated from the field layout.

Every crossing is projected into the image with the camera pose saved in the
frame. It gets a fixed-size box unless it is outside the image or mostly covered
by a labeled object.
"""
from lib import field


def _is_covered(frame, u, v, settings):
    mask = frame.instance_mask()
    if mask is None:
        return False
    half = settings["cover_window_px"] // 2
    ignored = set(settings["replace_labels"])
    total = covered = 0
    for y in range(max(0, int(v) - half), min(mask.height, int(v) + half + 1)):
        for x in range(max(0, int(u) - half), min(mask.width, int(u) + half + 1)):
            total += 1
            color = mask.pixel(x, y)
            if any(color[:3]) and frame.instance_label(color) not in ignored:
                covered += 1
    return total > 0 and covered / total > settings["max_covered_fraction"]


def process(frame, context):
    settings = context.settings["field_crossings"]
    ground_y = context.settings["field"]["ground_y"]
    layout = field.load(context)

    replaced = set(settings["replace_labels"])
    frame.boxes = [b for b in frame.boxes if b["labelName"] not in replaced]

    box_w = frame.width * settings["box_fraction"]
    box_h = frame.height * settings["box_fraction"]
    for label, points in layout.points.items():
        for point_u, point_v in points:
            x, z = layout.to_world(point_u, point_v)
            projected = frame.project((x, ground_y, z))
            if projected is None:
                continue
            u, v = projected
            if not (0 <= u < frame.width and 0 <= v < frame.height):
                continue
            if _is_covered(frame, u, v, settings):
                continue
            left = max(0.0, u - box_w / 2)
            top = max(0.0, v - box_h / 2)
            right = min(float(frame.width), u + box_w / 2)
            bottom = min(float(frame.height), v + box_h / 2)
            frame.boxes.append(
                {
                    "labelName": label,
                    "origin": [left, top],
                    "dimension": [right - left, bottom - top],
                    "point": [u, v],
                    "source": "field_crossings",
                }
            )
