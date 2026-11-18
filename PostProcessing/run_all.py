"""Run every post-processing step on one Perception SOLO run.

Usage:  python run_all.py <solo folder> [--out <folder>] [--overwrite] [--workers N]

The SOLO folder is only read. Results go to <solo folder>_post by default.
Steps and their settings are listed in config.json.
Frames are processed in parallel, one process per CPU thread by default.
"""
import argparse
import collections
import datetime
import importlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from lib import solo  # noqa: E402

FOLDERS = {
    "images": "RGB images, copied from the SOLO run",
    "labels": "One JSON per frame: boxes and camera",
    "segmentation": "Semantic mask per frame; colours are listed under segmentation_classes",
    "lines": "Field lines per frame: white = line",
    "pitch": "Visible grass per frame, field lines included: white = pitch (needs the depth labeler)",
    "depth": "Depth per frame for ControlNet: 8-bit grey, inverse depth scaled per image, near = white, sky = black",
    "checks/boxes": "Sample of frames with the boxes drawn on",
    "checks/segmentation": "Sample of frames with the segmentation blended over the image",
}


class Context:
    """What every step can use: settings, output folder and the size of the run."""

    def __init__(self, settings, out_dir, total_frames):
        self.settings = settings
        self.out_dir = out_dir
        self.total_frames = total_frames
        self.base_dir = BASE_DIR
        self.segmentation_classes = {}

    def path(self, folder, frame, extension):
        """Output file of a frame in one of the result folders, creating the folder if needed."""
        directory = os.path.join(self.out_dir, folder)
        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, frame.id + extension)

    def is_check_frame(self, frame):
        """True for the frames that get check images."""
        limit = self.settings["checks"]["max_images"]
        return frame.sequence % max(1, self.total_frames // limit) == 0


def _git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True, check=True
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", BASE_DIR], cwd=BASE_DIR, capture_output=True, text=True
        ).stdout.strip()
        return result.stdout.strip() + (" (with uncommitted changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


_worker = {}


def _init_worker(settings, out_dir, total_frames, run_name):
    """Runs once in every worker process."""
    _worker["context"] = Context(settings, out_dir, total_frames)
    _worker["steps"] = [importlib.import_module(f"steps.{name}") for name in settings["steps"]]
    _worker["run_name"] = run_name


def _process_frame(path):
    """All steps on one frame, then its image and label file. None if the frame has no capture."""
    context = _worker["context"]
    frame = solo.read_frame(path)
    if frame is None:
        return None
    frame.id = f"{_worker['run_name']}_{frame.sequence:06d}"
    context.segmentation_classes = {}
    for step in _worker["steps"]:
        step.process(frame, context)

    shutil.copyfile(frame.image_path, context.path("images", frame, ".png"))
    with open(context.path("labels", frame, ".json"), "w", encoding="utf8") as f:
        json.dump(
            {
                "id": frame.id,
                "image": f"images/{frame.id}.png",
                "segmentation": f"segmentation/{frame.id}.png",
                "depth": frame.depth_output,
                "width": frame.width,
                "height": frame.height,
                "camera": {
                    "position": frame.capture["position"],
                    "rotation": frame.capture["rotation"],
                    "matrix": frame.capture["matrix"],
                },
                "boxes": frame.boxes,
            },
            f,
            indent=1,
        )
    return [box["labelName"] for box in frame.boxes], context.segmentation_classes, frame.depth_path is not None


def main():
    parser = argparse.ArgumentParser(description="Run all post-processing steps on a SOLO run.")
    parser.add_argument("solo_dir")
    parser.add_argument("--out", help="output folder (default: <solo_dir>_post)")
    parser.add_argument("--overwrite", action="store_true", help="delete an existing output folder first")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1,
                        help="parallel processes (default: one per CPU thread; 1 = no parallelism)")
    args = parser.parse_args()

    solo_dir = os.path.abspath(args.solo_dir)
    out_dir = os.path.abspath(args.out) if args.out else solo_dir + "_post"
    if os.path.exists(out_dir) and os.listdir(out_dir):
        if not args.overwrite:
            sys.exit(f"{out_dir} already exists. Use --overwrite to replace it.")
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(BASE_DIR, "config.json"), encoding="utf8") as f:
        settings = json.load(f)
    steps = [importlib.import_module(f"steps.{name}") for name in settings["steps"]]  # for finish()

    run_name = os.path.basename(solo_dir)
    paths = solo.frame_paths(solo_dir)
    context = Context(settings, out_dir, len(paths))
    counts = collections.Counter()
    skipped = without_depth = 0
    started = time.time()

    workers = max(1, min(args.workers, len(paths) or 1))
    init = (settings, out_dir, len(paths), run_name)
    if workers == 1:
        _init_worker(*init)
        results = map(_process_frame, paths)
        pool = None
    else:
        pool = multiprocessing.Pool(workers, initializer=_init_worker, initargs=init)
        results = pool.imap_unordered(_process_frame, paths, chunksize=4)
    try:
        for index, result in enumerate(results, 1):
            if result is None:
                skipped += 1
            else:
                labels, classes, has_depth = result
                counts.update(labels)
                context.segmentation_classes.update(classes)
                without_depth += not has_depth
            if index % 100 == 0:
                print(f"{index}/{len(paths)} frames, {time.time() - started:.0f} s")
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    if without_depth:
        print(f"{without_depth} frame(s) have no depth image: no depth PNG and no pitch for them.")

    for step in steps:
        finish = getattr(step, "finish", None)
        if finish:
            finish(context)

    with open(os.path.join(solo_dir, "metadata.json"), encoding="utf8") as f:
        unity_metadata = json.load(f)
    metadata = {
        "run": run_name,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": solo_dir,
        "postprocessing_commit": _git_commit(),
        "frames": len(paths) - skipped,
        "frames_without_capture": skipped,
        "boxes": dict(sorted(counts.items())),
        "box_format": "origin = top-left corner [x, y] in pixels, dimension = [width, height] in pixels",
        "segmentation_classes": dict(sorted(context.segmentation_classes.items())),
        "folders": FOLDERS,
        "settings": settings,
        "unity": unity_metadata,
    }
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf8") as f:
        json.dump(metadata, f, indent=1)

    print(json.dumps({k: metadata[k] for k in ("run", "frames", "boxes", "segmentation_classes")}, indent=1))
    print(f"Done in {time.time() - started:.1f} s. Results: {out_dir}")


if __name__ == "__main__":
    main()
