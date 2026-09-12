# Interactive 3-Axis Taxel Array

> Standalone export (2026-09-12): this document preserves the original design
> history. Source paths and environment names below describe that historical
> workspace. The current standalone commands are in [README.md](README.md);
> the required aggregator is bundled at `tri_axis_array/code/estimate.py`.

- Author: Codex, with design approval from 浩阳
- Created: 2026-08-25
- Status: Approved for implementation
- Source of truth: this file

## Objective

Provide a small local interactive demonstration that makes the mapping from distributed per-taxel `[fx, fy, fz]` readings to a net six-component wrench physically visible and numerically checkable.

## Background

The hardware premise is a single sensing element that reports three force components but no local torque. Arranging multiple elements at known planar positions creates a discrete three-channel surface-force field. The existing `wrench/tri_axis_array/` slice already verifies the aggregation law

```text
F = sum_i f_i
M = sum_i (r_i - r_0) x f_i
```

and shows ideal observability of `Fx`, `Fy`, `Fz`, `Mx`, `My`, and `Mz`. The missing piece is a compact interactive view that lets the user change one taxel force and immediately see both the spatial field and the resulting wrench.

## Goals

- Let the user select any taxel in a runtime-configured planar array, defaulting to `3 x 3`.
- Let the user set signed `fx`, `fy`, and `fz` values for the selected taxel.
- Show `fz` as a scalar field and `fx/fy` as in-plane vectors.
- Recompute and display the net force and net moment after every change.
- Keep geometry and units explicit: force in N, positions in m, moments in N·m.
- Reuse the verified aggregation implementation from `wrench/tri_axis_array/code/estimate.py`.

## Non-goals

- No serial, CAN, ROS, CSV, or real-time hardware input in the first version.
- No interpolation into a continuous traction field.
- No compliance layer, sensor cross-talk model, calibration model, or uncertainty estimate.
- No local taxel torque measurement; moments arise only from force lever arms.
- No modification of the existing verified `tri_axis_array` experiment.

## Location and Components

Create the implementation inside this folder:

```text
tri_axis_array_interactive/
|- DESIGN.md
|- README.md
|- model.py
|- app.py
`- test_model.py
```

`model.py` owns the interactive state, grid geometry, shape validation, unit conversion, and delegation to the existing wrench aggregator. `app.py` owns Matplotlib layout and event callbacks. `test_model.py` checks mechanics invariants without opening a GUI. `README.md` records the command, controls, conventions, and current limitations.

## Data Contract

The force field uses:

```text
readings.shape == [rows, cols, 3]
readings[row, col] == [fx, fy, fz]  # N
```

The default centre pitch is `20 mm` in both axes, converted to metres before moment calculation. The array reference point is its geometric centre. The coordinate convention matches the existing experiment:

- `+x`: right across the displayed array
- `+y`: upward across the displayed array
- `+z`: outward normal
- `Mx`, `My`, `Mz`: right-hand-rule moments about the array centre

The default pitch is a configurable demonstration assumption, not a claim about the real sensor geometry.

## Interaction and Layout

The application starts with all taxel forces at zero.

1. The user clicks a taxel in the left plot.
2. Three sliders load that taxel's current `fx`, `fy`, and `fz` values.
3. Slider movement updates only the selected taxel.
4. The model recomputes the full wrench.
5. The plots redraw immediately.

The main force-field plot uses colour for `fz`, arrows for `fx/fy`, and an outline for the selected taxel. Net force and net moment use separate bar-chart axes because N and N·m must not share a quantitative scale. A compact selected-taxel label reports `(row, col)` and `[fx, fy, fz]`.

## Error Behaviour

- Reject force arrays that are not finite or do not match the configured `[rows, cols, 3]` shape.
- Reject non-positive pitch values.
- Fail with a clear message if NumPy, Matplotlib, or the sibling verified aggregator is unavailable.
- Ignore clicks outside the taxel grid.
- Keep UI callbacks deterministic: each event updates state once and redraws once.

## Verification

`test_model.py` uses the standard-library `unittest` runner and covers:

1. Zero field produces a zero wrench.
2. A centre normal force produces `Fz` but no moment.
3. An off-centre normal force produces the expected `Mx/My` signs and magnitudes.
4. A tangential force produces the expected `Fx/Fy` and lever-arm moment.
5. A balanced tangential pair produces a net `Mz` with zero net tangential force.
6. Invalid shape, non-finite input, and invalid pitch are rejected.

A headless Matplotlib smoke check creates the figure and performs one programmatic state update without requiring a display. Manual verification checks taxel selection, slider synchronisation, arrow direction, colour sign, and separate force/moment bar updates.

## Alternatives Considered

- Standalone HTML/JavaScript: visually flexible, but duplicates the verified mechanics in another language.
- Streamlit: quick controls, but adds a service process and dependency for a nine-taxel teaching tool.
- Matplotlib: selected because NumPy/Matplotlib already fit the project, the verified Python mechanics can be reused directly, and the result remains an offline one-command tool.

## Risks and Assumptions

- The demo visualises a discrete force field, not a continuously reconstructed traction field.
- Slider limits are presentation bounds, not sensor ratings.
- A common elastic cover could mechanically couple taxels in real hardware; this ideal demo deliberately excludes that effect.
- Full wrench observability assumes every taxel position and three-axis force vector are calibrated in one consistent coordinate frame.

## Acceptance Criteria

- `python app.py` opens the configured array view on a desktop Python environment.
- Clicking a taxel and changing any slider updates the correct force-map element.
- The displayed wrench matches the existing closed-form aggregator.
- Force and moment values display with correct, separate units.
- The targeted unit tests and headless GUI smoke check pass.

## Approved Live-Animation Extension

The second entry point adds continuous animation through the open-source Rerun Viewer while preserving the manual Matplotlib teaching tool.

```text
synthetic or sensor frame [3, 3, 3]
    -> latest force field
    -> existing TaxelArrayModel wrench aggregation
    -> Rerun Arrows3D + Points3D + six scalar time series
```

The first source is a deterministic moving Gaussian contact sampled at `30 Hz`. It creates non-negative normal load and a smaller rotating in-plane shear component so both the force field and all observable wrench branches move over time. The source contract remains a timestamp plus a finite `[3, 3, 3]` force array, allowing a later serial reader to replace the generator without changing visualization code.

`rerun_live.py` runs until interrupted by default, accepts a finite duration for verification, and can either spawn the native Viewer or save an `.rrd` recording without a GUI. Rerun is pinned to `rerun-sdk==0.36.2`. Because that release requires NumPy 2, it runs in an isolated `tactile-viz` environment; the existing `act-mujoco` environment remains on NumPy 1.26.4 for Matplotlib and MuJoCo compatibility.

Live acceptance criteria:

- The native Viewer receives animated per-taxel three-dimensional force arrows.
- Taxel point colour changes with `fz` without replacing the vector encoding.
- `Fx`, `Fy`, `Fz`, `Mx`, `My`, and `Mz` are logged on the same frame timeline.
- A finite headless run writes a non-empty `.rrd` file.
- Generated frames are deterministic, finite, correctly shaped, and bounded by the configured load scale.
- The existing Matplotlib application and its tests remain unchanged in behaviour.

## Approved Click-Linked PyQtGraph Extension

The owner selected a custom PyQtGraph window after confirming that the native Rerun desktop Viewer cannot send taxel selection callbacks to the Python producer. Rerun remains available as a recording and 3D-view option; the new `pyqt_live.py` entry point owns click-linked real-time inspection.

The window uses one dominant taxel field on the left and three synchronized plots on the right:

1. Net `Fx/Fy/Fz` in N.
2. Net `Mx/My/Mz` in N·m.
3. Selected taxel `fx/fy/fz` in N.

The field uses an `ImageItem` for `fz`, in-plane arrow glyphs for `fx/fy`, and an outline for the selected taxel. Clicking a cell maps the scene coordinate to `(row, col)`, updates the outline, and immediately redraws that taxel's complete buffered history rather than starting a new history at click time.

All live frontends share a pure `live_source.py` generator. The GUI stores a bounded rolling buffer containing timestamps, every `[3, 3, 3]` force field, and every six-component wrench. The default buffer covers ten seconds at 30 Hz. A Qt `QTimer` performs one frame generation, one model update, one history append, and one redraw per tick.

PyQtGraph is pinned to `0.14.0` with PySide6 `6.11.2` in a dedicated `taxel-pyqt` environment. It must remain separate from `tactile-viz`: Rerun's pyarrow stack installs Conda ICU libraries that conflict with pip Qt bindings on Windows. Headless verification uses `QT_QPA_PLATFORM=offscreen` and must cover timer-independent frame updates, click selection, history switching, curve values, bounded-buffer behaviour, and clean window construction.

## Approved Dynamic Geometry Contract

The owner confirmed that sample rate, array dimensions, and element spacing are design parameters while the communication format remains unknown. Geometry is therefore runtime configuration rather than module-level constants.

```text
rows, cols
pitch_x_mm, pitch_y_mm
taxel_width_x_mm, taxel_width_y_mm
hz
```

Defaults are `3 x 3`, `20 x 20 mm` taxel width, `20 x 20 mm` centre pitch, and `30 Hz`. The 20 mm size is a provisional visual and mechanics assumption, not a hardware claim. Width must not exceed pitch in either axis for the current non-overlapping planar layout.

Wrench aggregation uses taxel centre positions derived from pitch. Taxel width determines the rendered rectangle, total array footprint, and future force-to-traction area conversion; it does not alter the net force or lever-arm equations. Total footprint is:

```text
width_x = (cols - 1) * pitch_x + taxel_width_x
width_y = (rows - 1) * pitch_y + taxel_width_y
```

The frame contract becomes dynamic `[rows, cols, 3]`. A future communication adapter must yield a timestamp and a force field matching the configured geometry; serial, CSV, UDP, or vendor API parsing stays outside the model and visualizer.

## Approved Cloud Map View Extension (2026-09-10)

Objective: add a view-switching cloud-map mode to `pyqt_live.py` — two main buttons (Array/Cloud) switch the field plot, and in cloud mode a second exclusive row selects the channel. Default behaviour stays byte-identical to the array view unless the buttons or CLI (`--view cloud --cloud-channel mz`) are used.

Channels and moment contributions (per taxel, lever arms in metres about the array centre): `fz = readings[:,:,2]`, `shear = hypot(fx, fy)`, `mx = y_m*fz`, `my = -x_m*fz`, `mz = x_m*fy - y_m*fx`; `mx/my/mz` sums equal the verified wrench components.

Interpolation contract (`cloud_field.py`, pure NumPy, no Qt): separable Gaussian-weighted average over taxel centres with `sigma = 0.55 * pitch` per axis, sampled at 200 points per axis across the full footprint; weights normalize over finite taxels only (NaN taxels excluded as a future real-data seam); empty contributions become NaN. This is display interpolation only, not a physical traction-field reconstruction.

Fixed display ranges (no autoscale jitter): `fz`/`shear` use `[0, field_colour_max_n]`; moment channels use symmetric `±(peak_force_n * max(footprint_x_mm, footprint_y_mm) / 1000)`, shared with the moment plot YRange. Sequential LUT for force channels mirrors the discrete-view ramp; diverging blue-white-red for moments.

Verification: `test_cloud_field.py` covers the weight-normalization invariant (constant in = constant out), NaN exclusion, moment-sum equivalence to `TaxelArrayModel.wrench()` (rtol 1e-12), LUT midpoint/NaN/clamping behaviour, invalid-channel rejection, and non-square footprint extent; `test_pyqt_live.py` cloud tests cover mode switching, layer visibility, curve updates, channel switching, and invalid arguments.

### Polish (2026-09-11)

Three render-level refinements after hands-on use, all approved:

1. Cloud contrast: the cloud colour range now auto-scales by default (`cloud_scale="auto"` in the window, `--cloud-scale` on the CLI). Every cloud render tracks the strongest finite value of the active channel with instant attack and a smooth decay of half-life ~2 s (`decay = 0.5 ** (1.0 / max(1.0, hz * 2.0))` per frame), clamped to [5%, 100%] of the nominal ceiling (`field_colour_max_n` for `fz`/`shear`, `moment_limit` for moment channels). `set_cloud_channel` resets the running maximum so a previous channel's magnitude never leaks in, and the colourbar levels follow the live bound every frame. `--cloud-scale fixed` keeps the original fixed physical ranges byte-for-byte.
2. Selection marker: `set_view("cloud")` no longer hides the gold selection outline. Its zValue (20) already sits above the cloud image (-1), so the selected taxel stays visible and identifiable in both views.
3. Array gaps: when an axis has pitch == taxel width (the default 20/20 geometry), `_setup_field_plot` renders that dimension at 88% of the cell width, centred on the cell centre, so a fully pitched-out array still reads as discrete cells. Circle taxels take the inset only when both axes qualify. Geometries with a natural gap (pitch > width) render the true size. Hit-testing (`locate_taxel`) and the selection outline keep using the full logical cell; the model is untouched.


### Arrow alignment fix (2026-09-11)

Owner reported arrow heads misaligned with their lines whenever forces changed. Root cause: `makeArrowPath` builds the head pointing along -x with its tip at the anchor and `setStyle` rotates counter-clockwise in the y-up view, so the previous `angle = 180 - theta` rendered every head mirrored across the x-axis (invisible for pure +x forces, 90 deg off at +45 deg, reversed at +90 deg). Fixed to `angle = theta - 180`; `ArrowAlignmentTests` pins head direction to line direction for four off-axis forces (counter-proof: the old formula fails at exactly 90 deg).

### Verification fixes (2026-09-12)

The owner approved the five fixes identified in the frontend review. These
supersede the earlier frame-count timing and shared force-channel range rules:

1. Moment auto-scale tracks the largest absolute contribution, not the largest
   signed value. Mirrored positive normal loads and signed torsion now produce
   equal colourbar bounds.
2. `PreciseTimer` requests refreshes; the monotonic high-resolution
   `time.perf_counter()` clock supplies elapsed frame
   timestamps and drives simulated contact motion. The history buffer is bounded
   both by frame count and actual sample age. Missed ticks are not replaced with
   fabricated samples. Cloud decay uses actual elapsed seconds, including time
   away from cloud view; repeated rendering alone cannot accelerate decay.
3. Net-force plot bounds include configured shear of either sign. The net-moment
   range includes shear-generated torsion as well as normal-load moments.
4. Shear has its own cloud ceiling; changing shear does not inflate `Fz`, `Mx`,
   or `My` colour ranges. `Mz` includes the shear ceiling. Auto and fixed modes
   share the channel ceilings documented in [README.md](README.md).
5. The selected-taxel status is concise and wraps, allowing an 800-pixel-wide
   window without the previous long label forcing a wider minimum size.

Regression coverage uses the existing window/source boundary, displayed
colourbar and curve data, controlled clock delays, and window layout checks.
The wrench aggregator, sensor frame schema, and other viewer entry points are
unchanged. Dense-array rendering performance is outside this repair.
