# Interactive 3-Axis Taxel Array

Standalone export of the verified viewer from `every-embodied-main` commit
`7d73ad1`. Only the frontend and its required wrench aggregator are included;
the original research repository and Git history are not part of this project.
Run all commands below from this repository's root.

This folder shows how a planar array of single-point `[fx, fy, fz]` sensors forms a discrete three-channel force field and produces a net six-component wrench.

It now has four independent entry points:

- `pyqt_live.py`: continuous 30 Hz animation with click-linked per-taxel history.
- `pyqt_single_taxel.py`: a single sensor's three-channel force display and history.
- `rerun_live.py`: continuous 30 Hz animation in the Rerun Viewer.
- `app.py`: manual taxel selection and slider-based teaching view.

Sensor-side integration (frame contract, units, calibration expectations, and the
Python seam that replaces `live_source.py`) is specified in [INTEGRATION.md](INTEGRATION.md).

## Click-Linked Real-Time Window

Create the isolated Qt environment:

```powershell
conda create -n taxel-pyqt python=3.10 pip -y
conda run -n taxel-pyqt python -m pip install -r requirements-pyqt.txt
```

Run the PyQtGraph viewer:

```powershell
conda run -n taxel-pyqt python pyqt_live.py
```

The left field uses colour for `fz` and arrows for `fx/fy`. Click any cell to switch the right-bottom plot to that taxel's complete buffered `fx/fy/fz` history. The two upper plots remain the overall array force and moment, with ranges that include the configured positive or negative shear load. When pitch equals taxel width, cells render with a ~12% visual inset so the array structure stays visible (render-only; the click target is the full cell).

The Qt timer requests the configured refresh rate using `PreciseTimer`; this is a target, not a guaranteed acquisition rate. Frame timestamps and simulated contact motion use a monotonic clock, so missed ticks do not compress the time axis. History retains samples from at most the latest `--history-s` seconds (default 10), also capped at `ceil(hz * history_s)` frames. Delayed frames do not fabricate missing samples. The single-taxel viewer follows the same timer, monotonic-time, and age-bounded-history behaviour.

Uniform clamp-on-slider case with total `Fz=100 N` and total `Fx=40 N`:

```powershell
conda run -n taxel-pyqt python pyqt_live.py --scenario clamp-slider --peak-force-n 100 --tangential-force-n 40 --tangential-axis x --taxel-shape circle --pitch-x-mm 25 --pitch-y-mm 25 --taxel-width-x-mm 20 --taxel-width-y-mm 20
```

Example with a `2 x 4` array, rectangular taxels, and visible gaps:

```powershell
conda run -n taxel-pyqt python pyqt_live.py --rows 2 --cols 4 --pitch-x-mm 30 --pitch-y-mm 25 --taxel-width-x-mm 20 --taxel-width-y-mm 15 --hz 40
```

## Cloud Map View

The same viewer can switch the left field plot between the discrete taxel view (Array view) and an interpolated scalar cloud map (Cloud view) with the two buttons above the plot. In cloud mode a second exclusive button row selects the displayed channel: `Fz` (N), `|shear|` (N), and `Mx`, `My`, `Mz` (N·m, per-taxel moment contributions about the array centre). The right-side curves keep refreshing in both modes, and clicking still selects a taxel in either view.

```powershell
conda run -n taxel-pyqt python pyqt_live.py --view cloud --cloud-channel mz
```

The cloud is a Gaussian-weighted average over taxel centres with `sigma = 0.55 x pitch` per axis, sampled over the full array footprint. Colour ranges auto-scale by default: the strongest current value raises the range immediately, followed by a two-second half-life measured with the monotonic clock. Moment channels use the largest absolute value so positive and negative loads scale equally. Repainting or switching views without elapsed time does not decay the range.

The live bound is clamped to `[5%, 100%]` of a channel-specific nominal ceiling:

- `Fz`: `peak_force_n`, or `peak_force_n / active_divisor` in the clamp scenarios.
- `|shear|`: `0.22 * peak_force_n` for moving contact; `abs(tangential_force_n) / active_divisor` for clamp scenarios. Zero configured shear falls back to the `Fz` ceiling to keep a nonzero display range.
- `Mx`, `My`: `peak_force_n * L`, where `L = max(footprint_x_mm, footprint_y_mm) / 1000` in metres.
- `Mz`: `max(peak_force_n, total_shear_ceiling_n) * L`, including the configured shear magnitude.

The colourbar shows the live range. The same colour does NOT represent the same force value at different times in auto mode; use `--cloud-scale fixed` for quantitative colour comparisons across time. Fixed mode uses these channel ceilings throughout the run; they are display bounds, not sensor ratings. The gold selection marker stays visible in both views.

With edge-loaded contacts (for example `bottom-right-4`), the weighted average can place the brightest cloud region at the footprint corner nearest the loaded taxels; this is a display artifact. The true readings remain the discrete values at the taxel centres. Cloud smoothing does not reconstruct a continuous traction field or model mechanical cross-talk through a shared cover layer.

## Real-Time Animation

Keep the Rerun and Qt entry points in separate environments to avoid Windows
native-library conflicts. The optional Matplotlib entry point uses NumPy 1.26.
MuJoCo is not a dependency of this repository.

```powershell
conda create -n tactile-viz python=3.10 pip -y
conda run -n tactile-viz python -m pip install -r requirements-live.txt
```

Run indefinitely at 30 Hz; stop the producer with `Ctrl+C`:

```powershell
conda run -n tactile-viz python rerun_live.py
```

The moving Gaussian contact produces a normal-force patch plus rotating shear. The Rerun Viewer displays scaled 3D arrows at the taxel positions and six synchronized wrench curves. Arrow lengths are scaled by `0.004 m/N` for display; the logged force and moment values remain in N and N·m.

Create a finite recording without opening the Viewer:

```powershell
conda run -n tactile-viz python rerun_live.py --duration-s 5 --save-rrd tmp/taxel-live.rrd
```

## Manual Teaching View

Create the optional Matplotlib environment and launch from the repository root:

```powershell
conda create -n taxel-mpl python=3.10 pip -y
conda run -n taxel-mpl python -m pip install -r requirements-mpl.txt
conda run -n taxel-mpl python app.py
```

Optional geometry and display limits:

```powershell
conda run -n taxel-mpl python app.py --rows 3 --cols 3 --pitch-x-mm 20 --pitch-y-mm 20 --taxel-width-x-mm 20 --taxel-width-y-mm 20 --force-limit-n 5
```

The Matplotlib dependency pins match the locally verified runtime
(`numpy 1.26.4`, `matplotlib 3.9.4`, `TkAgg`). Use a separate environment rather
than mixing its binaries with the NumPy 2 Qt/Rerun environments.

## Controls

1. Click one of the nine taxels in the force-field plot.
2. Change its signed `fx`, `fy`, and `fz` values with the sliders.
3. Read the updated net force and net moment in their separate plots.

Colour represents `fz`; in-plane arrows represent `[fx, fy]`. The selected taxel has a gold outline. Arrow length is proportional to force and reaches approximately one cell at the configured slider limit.

## Coordinate and Unit Contract

- `+x`: right across the displayed array.
- `+y`: upward across the displayed array.
- `+z`: outward normal.
- Force components: N.
- Taxel positions: m internally.
- Moments: N·m about the array centre.
- Default layout: `3 x 3`, `20 x 20 mm` taxels, `20 x 20 mm` centre pitch.

The default pitch is a demonstration assumption, not a claim about the real sensor. The view is a discrete force field; it does not interpolate a continuous traction field or model mechanical cross-talk through a shared cover layer.

## Verify

```powershell
conda run -n taxel-mpl python -m unittest test_model -v
```

The PyQt viewer tests run in their own environment (`test_model` and
`test_rerun_live` belong to the `taxel-mpl` and `tactile-viz` environments):

```powershell
conda run -n taxel-pyqt python -m unittest test_cloud_field test_pyqt_live test_pyqt_single_taxel test_review_regressions -v
```

The tests cover zero load, centred and off-centred normal load, tangential lever arms, a pure torsional shear pair, invalid input, headless figure updates, real-time history behaviour, and arrow-direction regressions.

Run the Rerun generator and recording checks separately in its isolated environment:

```powershell
conda run -n tactile-viz python -m unittest test_rerun_live -v
```
