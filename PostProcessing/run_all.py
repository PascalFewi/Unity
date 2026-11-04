"""Run every post-processing step on one Perception SOLO run.

Usage:  python run_all.py <solo folder> [--out <folder>]

The SOLO folder is only read. Results go to <solo folder>_post by default.
Steps and their settings are listed in config.json.
"""
import argparse
import collections
import importlib
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from lib import solo  # noqa: E402


class Context:
    """What every step can use: settings, output folder and the size of the run."""

    def __init__(self, settings, out_dir, total_frames):
        self.settings = settings
        self.out_dir = out_dir
        self.total_frames = total_frames
        self.base_dir = BASE_DIR


def main():
    parser = argparse.ArgumentParser(description="Run all post-processing steps on a SOLO run.")
    parser.add_argument("solo_dir")
    parser.add_argument("--out", help="output folder (default: <solo_dir>_post)")
    args = parser.parse_args()

    solo_dir = os.path.abspath(args.solo_dir)
    out_dir = os.path.abspath(args.out) if args.out else solo_dir + "_post"
    labels_dir = os.path.join(out_dir, "labels")
    os.makedirs(labels_dir, exist_ok=True)

    with open(os.path.join(BASE_DIR, "config.json"), encoding="utf8") as f:
        settings = json.load(f)
    steps = [importlib.import_module(f"steps.{name}") for name in settings["steps"]]

    paths = solo.frame_paths(solo_dir)
    context = Context(settings, out_dir, len(paths))
    counts = collections.Counter()
    skipped = 0
    started = time.time()

    for index, path in enumerate(paths, 1):
        frame = solo.read_frame(path)
        if frame is None:
            skipped += 1
            continue
        for step in steps:
            step.process(frame, context)
        counts.update(box["labelName"] for box in frame.boxes)
        with open(os.path.join(labels_dir, f"sequence.{frame.sequence}.json"), "w", encoding="utf8") as f:
            json.dump(
                {
                    "sequence": frame.sequence,
                    "image": os.path.relpath(frame.image_path, solo_dir).replace(os.sep, "/"),
                    "width": frame.width,
                    "height": frame.height,
                    "boxes": frame.boxes,
                },
                f,
                indent=1,
            )
        if index % 100 == 0:
            print(f"{index}/{len(paths)} frames")

    for step in steps:
        finish = getattr(step, "finish", None)
        if finish:
            finish(context)

    summary = {
        "solo_dir": solo_dir,
        "steps": settings["steps"],
        "frames": len(paths) - skipped,
        "frames_without_capture": skipped,
        "boxes": dict(sorted(counts.items())),
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf8") as f:
        json.dump(summary, f, indent=1)

    print(json.dumps(summary, indent=1))
    print(f"Done in {time.time() - started:.1f} s. Results: {out_dir}")


if __name__ == "__main__":
    main()
