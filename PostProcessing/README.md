# Post-processing

Steps that run on a finished Unity Perception (SOLO) run. They only read the SOLO folder, so a run can be processed again at any time.

## Run

Needs Python 3.8 or newer. Nothing else has to be installed.

```
python run_all.py <solo folder>
```

Results go to `<solo folder>_post`. If that folder already exists, add `--overwrite` to replace it. Use `--out <folder>` to choose another output folder.

## Output

Every frame has an id `<run>_<sequence>`, for example `solo_29_000012`, and the same file name in every folder.

| Path | Content |
|---|---|
| `images/<id>.png` | RGB image, copied from the SOLO run |
| `labels/<id>.json` | Boxes and camera of the frame (see below) |
| `segmentation/<id>.png` | Semantic mask: one colour per class, including the field lines. Colours are in `metadata.json`. |
| `lines/<id>.png` | Field lines only: white = line, black = rest |
| `checks/boxes/<id>.png` | Sample of frames with the boxes drawn on |
| `checks/segmentation/<id>.png` | Sample of frames with the segmentation blended over the image |
| `metadata.json` | Whole run: source, post-processing commit, frame count, boxes per class, segmentation colours, settings, Unity metadata |

### labels/&lt;id&gt;.json

```json
{
 "id": "solo_29_000012",
 "image": "images/solo_29_000012.png",
 "segmentation": "segmentation/solo_29_000012.png",
 "width": 640, "height": 480,
 "camera": {"position": [x, y, z], "rotation": [x, y, z, w], "matrix": [...]},
 "boxes": [
  {"labelName": "robot", "origin": [x, y], "dimension": [w, h], "source": "perception"},
  {"labelName": "T-Intersection", "origin": [x, y], "dimension": [w, h], "point": [u, v], "source": "field_crossings"}
 ]
}
```

- `origin` is the top-left corner and `dimension` is width and height, both in pixels.
- `point` is the exact crossing position; only crossings and penalty points have it.
- `camera` is the Unity camera pose and projection, as saved by Perception.

## Steps

`config.json` lists the steps in the order they run, and the settings of each step. Shared field settings are under `field`.

| Step | What it does |
|---|---|
| `field_crossings` | Replaces Perception's crossing boxes with calculated ones, and adds `PenaltyPoint` |
| `segmentation` | Adds the field lines to Perception's semantic mask and removes specks of the buried crossing objects |
| `check_images` | Draws the boxes on a sample of frames. Keep it last so it shows the final boxes. |

### field_crossings

The crossing objects in the scene lie mostly below the grass, so Perception sees few of them. The visible lines are a decal and can't be labeled. This step therefore uses the known position of each crossing:

1. It projects each point in `data/field_layout.json` into the image, using the camera pose saved in the frame.
2. It skips points outside the image, and points where more than half of a small window is covered by a labeled object.
3. It adds a box of fixed size around the point: `box_fraction` of the image width and height.

### segmentation

The field lines from `data/field_layout.json` are drawn into each frame with the saved camera pose. Pixels covered by a labeled object are removed. Lines stay at least 1 pixel wide, so distant lines don't break up.

### Limits

- Only labeled objects count as covering a crossing or a line, so boards and banners don't.
- Positions match the field image and Decal Projector in `K1Scene`. If either changes, update `data/field_layout.json`. If the grass height changes, update `ground_y` under `field` in `config.json`.

## Add a step

1. Create `steps/my_step.py` with this function. It runs once per frame and can change `frame.boxes`:

   ```python
   def process(frame, context):
       settings = context.settings["my_step"]
       ...
   ```

   For work at the end of the run, also add `def finish(context):`.

2. Add `"my_step"` to `steps` in `config.json`, in the position it should run, and add a `"my_step"` block with its settings.

`frame` is defined in `lib/solo.py`; `frame.id` is the frame id. `context` gives access to `settings`, `out_dir` and `total_frames`. Use `context.path(folder, frame, ".png")` for output files and `context.is_check_frame(frame)` to pick the check-image sample.
