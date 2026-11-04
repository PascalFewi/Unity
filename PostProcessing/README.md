# Post-processing

Steps that run on a finished Unity Perception (SOLO) run. They only read the SOLO folder, so a run can be processed again at any time.

## Run

Needs Python 3.8 or newer. Nothing else has to be installed.

```
python run_all.py <solo folder>
```

Results go to `<solo folder>_post`:

| Path | Content |
|---|---|
| `labels/sequence.N.json` | All boxes of frame N. `origin` is the top-left corner and `dimension` is width and height, both in pixels. |
| `masks/lines/sequence.N.png` | Field lines in white on black |
| `masks/semantic_lines/sequence.N.png` | Perception's semantic mask with the field lines added |
| `check_images/` | A sample of frames with the boxes drawn on, for checking by eye |
| `check_lines/` | A sample of frames with the line mask drawn in red, for checking by eye |
| `summary.json` | Frames processed and boxes per class |

Use `--out <folder>` to choose another output folder.

## Steps

`config.json` lists the steps in the order they run, and the settings of each step.

| Step | What it does |
|---|---|
| `field_crossings` | Replaces Perception's crossing boxes with calculated ones, and adds `PenaltyPoint` |
| `line_mask` | Creates a mask of the field lines |
| `check_images` | Draws the boxes on a sample of frames. Keep it last so it shows the final boxes. |

### field_crossings

The crossing objects in the scene lie mostly below the grass, so Perception sees few of them. The visible lines are a decal and can't be labeled. This step therefore uses the known position of each crossing:

1. It projects each point in `data/field_layout.json` into the image, using the camera pose saved in the frame.
2. It skips points outside the image, and points where more than half of a small window is covered by a labeled object.
3. It adds a box of fixed size around the point: `box_fraction` of the image width and height. Each box also stores the exact `point`.

Objects without a label, such as boards and banners, don't count as covering a crossing.

If the Decal Projector or its field image changes, update `data/field_layout.json`. If the height of the grass changes, update `ground_y` under `field` in `config.json`.

### line_mask

The field lines are a decal, so Perception can't mask them. This step draws the lines from `data/field_layout.json` into each frame using the saved camera pose, then removes pixels covered by a labeled object in the semantic mask. Lines stay at least 1 pixel wide, so distant lines don't break up.

Objects without a label, such as boards and banners, don't count as covering a line.

## Add a step

1. Create `steps/my_step.py` with this function. It runs once per frame and can change `frame.boxes`:

   ```python
   def process(frame, context):
       settings = context.settings["my_step"]
       ...
   ```

   For work at the end of the run, also add `def finish(context):`.

2. Add `"my_step"` to `steps` in `config.json`, in the position it should run, and add a `"my_step"` block with its settings.

`frame` is defined in `lib/solo.py`. `context` gives access to `settings`, `out_dir`, `total_frames` and `base_dir`. Steps write any extra files to `context.out_dir`.
