"""Read Unity Perception SOLO runs. Nothing in a SOLO folder is ever modified."""
import glob
import json
import os
import re

from lib import exr, png


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
        self._semantic_annotation = None
        self._semantic_mask = None
        self.depth_path = None
        self.depth_output = None
        self._depth = None

        for annotation in capture["annotations"]:
            kind = annotation["@type"]
            if "DepthAnnotation" in kind:
                self.depth_path = os.path.join(self.folder, annotation["filename"])
            elif "BoundingBox2D" in kind:
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
            elif "SemanticSegmentation" in kind:
                self._semantic_annotation = annotation

    def to_camera(self, point):
        """World point (Unity coordinates) to camera coordinates. z is the distance ahead."""
        delta = [p - c for p, c in zip(point, self.capture["position"])]
        return _rotate_inverse(self.capture["rotation"], delta)

    def camera_to_pixel(self, point):
        """Camera coordinates with z > 0 to (u, v) in pixels."""
        x, y, z = point
        fx = self.capture["matrix"][0]
        fy = self.capture["matrix"][4]
        return (
            (0.5 + 0.5 * fx * x / z) * self.width,
            (0.5 - 0.5 * fy * y / z) * self.height,
        )

    def project(self, point):
        """World point (Unity coordinates) to (u, v) in pixels. None if behind the camera."""
        camera = self.to_camera(point)
        if camera[2] <= 0.05:
            return None
        return self.camera_to_pixel(camera)

    def depth(self):
        """Depth image (height x width, float32 meters, 0 = nothing hit), or None if this run has none."""
        if self.depth_path is None:
            return None
        if self._depth is None:
            self._depth = exr.read_channel(self.depth_path, "R")
        return self._depth

    def camera_axes(self):
        """The camera's right, up and forward directions in world coordinates."""
        q = self.capture["rotation"]
        return [_rotate(q, axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]

    def semantic_classes(self):
        """Classes in this frame's semantic mask: name -> (r, g, b, a)."""
        return {i["labelName"]: i["pixelValue"] for i in self._semantic_annotation.get("instances", [])}

    def semantic_mask(self):
        """Semantic segmentation image (height x width x 4, uint8)."""
        if self._semantic_mask is None:
            path = os.path.join(self.folder, self._semantic_annotation["filename"])
            self._semantic_mask = png.read(path)
        return self._semantic_mask

    def instance_mask(self):
        """Instance segmentation image (height x width x 4, uint8), or None if this run has none."""
        if self._instance_mask is None and self._instance_annotation is not None:
            path = os.path.join(self.folder, self._instance_annotation["filename"])
            self._instance_mask = png.read(path)
        return self._instance_mask

    def instance_labels(self):
        """Instance colours (r, g, b, a) -> label name."""
        return {tuple(i["color"]): i["labelName"] for i in self._instance_annotation.get("instances", [])}


def _rotate_inverse(q, v):
    # Rotate v by the conjugate of quaternion q = (x, y, z, w).
    return _rotate((-q[0], -q[1], -q[2], q[3]), v)


def _rotate(q, v):
    # Rotate v by quaternion q = (x, y, z, w).
    x, y, z, w = q
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
