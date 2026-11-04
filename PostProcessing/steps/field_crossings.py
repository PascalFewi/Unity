"""Replace Perception's crossing boxes with boxes calculated from the field layout.

Every crossing is projected into the image with the camera pose saved in the
frame. It gets a fixed-size box unless it is outside the image or mostly covered
by a labeled object.
"""
import json
import os

_world_points_cache = None


def _world_points(settings, base_dir):
    global _world_points_cache
    if _world_points_cache is None:
        with open(os.path.join(base_dir, settings["layout"]), encoding="utf8") as f:
            layout = json.load(f)
        decal = layout["decal"]
        center_u, center_v = decal["center_pixel"]
        scale = decal["pixels_per_meter"]
        _world_points_cache = [
            (
                label,
                decal["center_world_x"] + (u - center_u) / scale,
                decal["center_world_z"] + (center_v - v) / scale,
            )
            for label, points in layout["points"].items()
            for u, v in points
        ]
    return _world_points_cache


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
    replaced = set(settings["replace_labels"])
    frame.boxes = [b for b in frame.boxes if b["labelName"] not in replaced]

    box_w = frame.width * settings["box_fraction"]
    box_h = frame.height * settings["box_fraction"]
    for label, x, z in _world_points(settings, context.base_dir):
        projected = frame.project((x, settings["ground_y"], z))
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
