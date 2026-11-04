"""Read Unity Perception SOLO runs. Nothing in a SOLO folder is ever modified."""
import glob
import json
import os
import re

from lib import png


class Frame:
    def __init__(self, data_path, capture):
        self.data_path = data_path
        self.folder = os.path.dirname(data_path)
        self.sequence = int(re.search(r"sequence\.(\d+)", self.folder).group(1))
        self.capture = capture
        self.width, self.height = (int(v) for v in capture["dimension"])
        self.image_path = os.path.join(self.folder, capture["filename"])
        self.boxes = []
        self._instance_annotation = None
        self._instance_mask = None

        for annotation in capture["annotations"]:
            kind = annotation["@type"]
            if "BoundingBox2D" in kind:
                self.boxes = [
                    {
                        "labelName": v["labelName"],
                        "origin": v["origin"],
                        "dimension": v["dimension"],
                        "source": "perception",
                    }
                    for v in annotation.get("values", [])
                ]
            elif "InstanceSegmentation" in kind:
                self._instance_annotation = annotation

    def project(self, point):
        """World point (Unity coordinates) to (u, v) in pixels. None if behind the camera."""
        delta = [p - c for p, c in zip(point, self.capture["position"])]
        x, y, z = _rotate_inverse(self.capture["rotation"], delta)
        if z <= 0.05:
            return None
        fx = self.capture["matrix"][0]
        fy = self.capture["matrix"][4]
        return (
            (0.5 + 0.5 * fx * x / z) * self.width,
            (0.5 - 0.5 * fy * y / z) * self.height,
        )

    def instance_mask(self):
        """Instance segmentation image, or None if this run has none."""
        if self._instance_mask is None and self._instance_annotation is not None:
            path = os.path.join(self.folder, self._instance_annotation["filename"])
            self._instance_mask = png.read(path)
        return self._instance_mask

    def instance_label(self, color):
        """Label of an instance colour (r, g, b, a) from the instance mask."""
        for instance in self._instance_annotation.get("instances", []):
            if tuple(instance["color"]) == tuple(color):
                return instance["labelName"]
        return None


def _rotate_inverse(q, v):
    # Rotate v by the conjugate of quaternion q = (x, y, z, w).
    x, y, z, w = -q[0], -q[1], -q[2], q[3]
    tx = 2 * (y * v[2] - z * v[1])
    ty = 2 * (z * v[0] - x * v[2])
    tz = 2 * (x * v[1] - y * v[0])
    return (
        v[0] + w * tx + y * tz - z * ty,
        v[1] + w * ty + z * tx - x * tz,
        v[2] + w * tz + x * ty - y * tx,
    )


def frame_paths(solo_dir):
    """All frame_data files, ordered by sequence number."""
    paths = glob.glob(os.path.join(solo_dir, "sequence.*", "step*.frame_data.json"))
    return sorted(paths, key=lambda p: int(re.search(r"sequence\.(\d+)", p).group(1)))


def read_frame(data_path):
    """The camera frame stored in a frame_data file, or None if it has no capture."""
    with open(data_path, encoding="utf8") as f:
        captures = json.load(f).get("captures")
    if not captures:
        return None
    return Frame(data_path, captures[0])
