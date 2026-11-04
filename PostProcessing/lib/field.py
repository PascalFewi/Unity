"""Field layout: positions of lines and crossings, converted to Unity world coordinates."""
import json
import os

_cache = {}


class Layout:
    def __init__(self, data):
        decal = data["decal"]
        self._center_x = decal["center_world_x"]
        self._center_z = decal["center_world_z"]
        self._center_u, self._center_v = decal["center_pixel"]
        self._scale = decal["pixels_per_meter"]
        self.points = data["points"]
        self.line_width = data["line_width_m"]
        self.lines = data["lines"]
        self.circles = data["circles"]
        self.spots = data["spots"]

    def to_world(self, u, v):
        """Position in the field image to world (x, z)."""
        return (
            self._center_x + (u - self._center_u) / self._scale,
            self._center_z + (self._center_v - v) / self._scale,
        )

    def length(self, pixels):
        """Length in the field image to meters."""
        return pixels / self._scale


def load(context):
    path = os.path.join(context.base_dir, context.settings["field"]["layout"])
    if path not in _cache:
        with open(path, encoding="utf8") as f:
            _cache[path] = Layout(json.load(f))
    return _cache[path]
