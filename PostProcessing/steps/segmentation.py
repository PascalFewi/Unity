"""Build the final segmentation: Perception's semantic mask plus the field lines.

The field lines are a decal, so Perception can't mask them. They are drawn into
each frame from the field layout with the saved camera pose, and pixels covered
by a labeled object are removed. Distant lines stay at least 1 pixel wide.
Leftover specks of the buried crossing objects are removed from the mask.
If the run has depth images, the visible grass is added as the pitch class
(labeled objects win over lines, lines win over the pitch).

Writes per frame:
  segmentation/<id>.png          semantic mask with the lines and the pitch added
  lines/<id>.png                 field lines only: white = line
  pitch/<id>.png                 visible grass including the lines: white = pitch (needs depth)
  checks/segmentation/<id>.png   (sample) segmentation blended over the image
"""
import math

import numpy as np

from lib import field, png

_NEAR = 0.05


def _shapes(layout, circle_segments):
    """Every line piece as ((x1, z1), (x2, z2), width) in meters."""
    shapes = []
    width = layout.line_width
    for u1, v1, u2, v2 in layout.lines:
        start = layout.to_world(u1, v1)
        end = layout.to_world(u2, v2)
        length = math.dist(start, end)
        ex = (end[0] - start[0]) / length * width / 2
        ez = (end[1] - start[1]) / length * width / 2
        shapes.append(((start[0] - ex, start[1] - ez), (end[0] + ex, end[1] + ez), width))
    for u, v, radius in layout.circles:
        center_x, center_z = layout.to_world(u, v)
        radius_m = layout.length(radius)
        ring = [
            (
                center_x + radius_m * math.cos(2 * math.pi * i / circle_segments),
                center_z + radius_m * math.sin(2 * math.pi * i / circle_segments),
            )
            for i in range(circle_segments + 1)
        ]
        shapes.extend((a, b, width) for a, b in zip(ring, ring[1:]))
    for u, v, size in layout.spots:
        x, z = layout.to_world(u, v)
        half = layout.length(size) / 2
        shapes.append(((x - half, z), (x + half, z), half * 2))
    return shapes


def _clip_near(polygon):
    """Keep the part of a polygon in front of the camera."""
    clipped = []
    for i, current in enumerate(polygon):
        following = polygon[(i + 1) % len(polygon)]
        if current[2] >= _NEAR:
            clipped.append(current)
        if (current[2] >= _NEAR) != (following[2] >= _NEAR):
            t = (_NEAR - current[2]) / (following[2] - current[2])
            clipped.append(tuple(c + t * (f - c) for c, f in zip(current, following)))
    return clipped


def _fill_polygon(mask, points):
    height, width = mask.shape
    top = max(0, int(math.floor(min(p[1] for p in points))))
    bottom = min(height - 1, int(math.ceil(max(p[1] for p in points))))
    for y in range(top, bottom + 1):
        sample = y + 0.5
        crossings = []
        for i, (x1, y1) in enumerate(points):
            x2, y2 = points[(i + 1) % len(points)]
            if (y1 <= sample) != (y2 <= sample):
                crossings.append(x1 + (sample - y1) / (y2 - y1) * (x2 - x1))
        crossings.sort()
        for left, right in zip(crossings[::2], crossings[1::2]):
            start = max(0, int(math.floor(left)))
            end = min(width - 1, int(math.ceil(right)))
            if start <= end:
                mask[y, start:end + 1] = 255


def _draw_line(mask, start, end):
    steps = int(max(abs(end[0] - start[0]), abs(end[1] - start[1]))) + 1
    i = np.arange(steps + 1)
    x = (start[0] + (end[0] - start[0]) * i / steps).astype(np.int64)
    y = (start[1] + (end[1] - start[1]) * i / steps).astype(np.int64)
    inside = (x >= 0) & (x < mask.shape[1]) & (y >= 0) & (y < mask.shape[0])
    mask[y[inside], x[inside]] = 255


def _draw_shape(frame, mask, shape, ground_y):
    start, end, width = shape
    dx, dz = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dz)
    nx = -dz / length * width / 2
    nz = dx / length * width / 2
    corners = [
        (start[0] + nx, ground_y, start[1] + nz),
        (end[0] + nx, ground_y, end[1] + nz),
        (end[0] - nx, ground_y, end[1] - nz),
        (start[0] - nx, ground_y, start[1] - nz),
    ]
    camera = _clip_near([frame.to_camera(c) for c in corners])
    if len(camera) < 3:
        return
    pixels = [frame.camera_to_pixel(c) for c in camera]
    if (
        max(p[0] for p in pixels) < 0
        or min(p[0] for p in pixels) >= frame.width
        or max(p[1] for p in pixels) < 0
        or min(p[1] for p in pixels) >= frame.height
    ):
        return
    _fill_polygon(mask, pixels)

    center = _clip_near([frame.to_camera((start[0], ground_y, start[1])), frame.to_camera((end[0], ground_y, end[1]))])
    if len(center) >= 2:
        _draw_line(mask, frame.camera_to_pixel(center[0]), frame.camera_to_pixel(center[1]))


def _pitch_mask(frame, layout, ground_y, tolerance):
    """White where the visible surface is the grass: on the ground and inside the grass area.

    Every pixel's world position comes from its depth and the camera pose, so anything
    standing on the grass hides it, labeled or not. None if the run has no depth.
    """
    depth = frame.depth()
    if depth is None:
        return None
    height, width = depth.shape
    min_x, max_x, min_z, max_z = layout.pitch_bounds()
    right, up, forward = frame.camera_axes()
    px, py, pz = frame.capture["position"]
    fx, fy = frame.capture["matrix"][0], frame.capture["matrix"][4]

    # World direction of each pixel's ray, scaled so that depth * direction = offset from the camera.
    a = ((np.arange(width) + 0.5) / width - 0.5) * 2 / fx
    b = ((0.5 - (np.arange(height) + 0.5) / height) * 2 / fy)[:, None]
    d = depth.astype(np.float64)
    y = py + d * ((forward[1] + b * up[1]) + a * right[1])
    x = px + d * ((forward[0] + b * up[0]) + a * right[0])
    z = pz + d * ((forward[2] + b * up[2]) + a * right[2])
    on_pitch = (d > 0) & (np.abs(y - ground_y) <= tolerance)
    on_pitch &= (x >= min_x) & (x <= max_x) & (z >= min_z) & (z <= max_z)
    return np.where(on_pitch, 255, 0).astype(np.uint8)


def _has_color(image, color):
    """Pixels whose RGB equals color."""
    return np.all(image[:, :, :3] == np.asarray(color, dtype=np.uint8), axis=2)


def process(frame, context):
    settings = context.settings["segmentation"]
    ground_y = context.settings["field"]["ground_y"]
    layout = field.load(context)

    lines = np.zeros((frame.height, frame.width), dtype=np.uint8)
    for shape in _shapes(layout, settings["circle_segments"]):
        _draw_shape(frame, lines, shape, ground_y)

    result = frame.semantic_mask().copy()
    for name, color in frame.semantic_classes().items():
        if name in settings["remove_labels"]:
            result[_has_color(result, color[:3]), :3] = 0
        else:
            context.segmentation_classes[name] = list(color[:3])

    # Labeled objects win over the lines.
    context.segmentation_classes[settings["line_label"]] = list(settings["line_color"])
    lines[result[:, :, :3].any(axis=2)] = 0
    result[lines > 0, :3] = settings["line_color"]

    # Lines win over the pitch; the pitch mask keeps the lines but not labeled objects.
    pitch = _pitch_mask(frame, layout, ground_y, settings["pitch_tolerance_m"])
    if pitch is not None:
        context.segmentation_classes[settings["pitch_label"]] = list(settings["pitch_color"])
        on_pitch = pitch > 0
        empty = ~result[:, :, :3].any(axis=2)
        pitch[on_pitch & ~empty & ~_has_color(result, settings["line_color"])] = 0
        result[on_pitch & empty, :3] = settings["pitch_color"]
        png.write(context.path("pitch", frame, ".png"), pitch)

    png.write(context.path("segmentation", frame, ".png"), result)
    png.write(context.path("lines", frame, ".png"), lines)
    if context.is_check_frame(frame):
        _write_check(frame, result, context)


def _write_check(frame, segmentation, context):
    image = png.read(frame.image_path).copy()
    colored = segmentation[:, :, :3].any(axis=2)
    blend = (image[:, :, :3].astype(np.uint16) + segmentation[:, :, :3]) // 2
    image[colored, :3] = blend[colored].astype(np.uint8)
    png.write(context.path("checks/segmentation", frame, ".png"), image)
