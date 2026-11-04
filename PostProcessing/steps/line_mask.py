"""Create a mask of the field lines, which Perception can't label because they are a decal.

Lines from the field layout are drawn into the image with the camera pose saved
in the frame. Pixels covered by a labeled object are removed using the semantic
mask. Distant lines are always drawn at least 1 pixel wide, so they stay unbroken.

Output, by sequence number:
  masks/lines/             white lines on black
  masks/semantic_lines/    Perception's semantic mask with the lines added
  check_lines/             sample of frames with the lines drawn in red
"""
import math
import os

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
    width, height = mask.width, mask.height
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
                row = y * width
                mask.pixels[row + start:row + end + 1] = b"\xff" * (end - start + 1)


def _draw_line(mask, start, end):
    steps = int(max(abs(end[0] - start[0]), abs(end[1] - start[1]))) + 1
    for i in range(steps + 1):
        x = int(start[0] + (end[0] - start[0]) * i / steps)
        y = int(start[1] + (end[1] - start[1]) * i / steps)
        if 0 <= x < mask.width and 0 <= y < mask.height:
            mask.pixels[y * mask.width + x] = 255


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


def _line_pixels(mask):
    position = mask.pixels.find(255)
    while position != -1:
        yield position
        position = mask.pixels.find(255, position + 1)


def process(frame, context):
    settings = context.settings["line_mask"]
    ground_y = context.settings["field"]["ground_y"]
    layout = field.load(context)

    mask = png.Image(frame.width, frame.height, 1, bytearray(frame.width * frame.height))
    for shape in _shapes(layout, settings["circle_segments"]):
        _draw_shape(frame, mask, shape, ground_y)

    semantic = frame.semantic_mask()
    combined = png.Image(frame.width, frame.height, semantic.channels, bytearray(semantic.pixels))
    color = bytes(settings["line_color"])
    channels = semantic.channels
    for position in _line_pixels(mask):
        start = position * channels
        if any(semantic.pixels[start:start + 3]):
            mask.pixels[position] = 0
        else:
            combined.pixels[start:start + 3] = color

    _write(context, "lines", frame, mask)
    _write(context, "semantic_lines", frame, combined)
    _write_check(frame, mask, context)


def _write(context, name, frame, image):
    folder = os.path.join(context.out_dir, "masks", name)
    os.makedirs(folder, exist_ok=True)
    png.write(os.path.join(folder, f"sequence.{frame.sequence}.png"), image)


def _write_check(frame, mask, context):
    limit = context.settings["check_images"]["max_images"]
    if frame.sequence % max(1, context.total_frames // limit) != 0:
        return
    image = png.read(frame.image_path)
    for position in _line_pixels(mask):
        start = position * image.channels
        image.pixels[start:start + 3] = b"\xff\x00\x00"
    folder = os.path.join(context.out_dir, "check_lines")
    os.makedirs(folder, exist_ok=True)
    png.write(os.path.join(folder, f"sequence.{frame.sequence}.png"), image)
