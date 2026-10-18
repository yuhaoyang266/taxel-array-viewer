# Interactive 3-Axis Taxel Array Viewer

> Interactive 2D/3D visualization and wrench aggregation testbed for planar 3-axis taxel sensor arrays (`[fx, fy, fz]` &rarr; 6-axis net wrench `[Fx, Fy, Fz, Mx, My, Mz]`).

This repository provides standalone interactive viewers and real-time animation tools for planar tactile arrays. It visualizes how discrete 3-axis force measurements form a surface force field and compute the net contact wrench about the array geometric centre.

---

## Quickstart

Run the default PyQtGraph real-time viewer (30 Hz continuous contact simulation with interactive taxel history):

```powershell
# In the taxel-pyqt environment:
python pyqt_live.py
```

- **Left field**: Discrete taxel view — cell colour represents normal force $f_z$, in-plane arrows represent tangential shear $[f_x, f_y]$.
- **Right curves**: Top two plots show net forces ($F_x, F_y, F_z$) and net moments ($M_x, M_y, M_z$).
- **Interaction**: Click any taxel cell to inspect its rolling buffered $[f_x, f_y, f_z]$ history in the bottom-right plot.

---

## Entry Points & Usage

The repository provides four entry points tailored for different inspection and integration workflows:

| Entry Point | Runtime Engine | Primary Use Case | Example Command |
|---|---|---|---|
| [`pyqt_live.py`](pyqt_live.py) | PyQtGraph / PySide6 | Real-time array monitoring & click-linked taxel inspection | `python pyqt_live.py` |
| [`pyqt_single_taxel.py`](pyqt_single_taxel.py) | PyQtGraph / PySide6 | Single-taxel 3-axis live response & shear magnitude tracking | `python pyqt_single_taxel.py` |
| [`rerun_live.py`](rerun_live.py) | Rerun SDK | 3D spatial field arrows & synchronized wrench recording | `python rerun_live.py` |
| [`app.py`](app.py) | Matplotlib / TkAgg | Offline manual taxel force editing & mechanics teaching | `python app.py` |

### 1. PyQt Real-Time Array Viewer (`pyqt_live.py`)

Simulates or ingests live contact frames with dynamic history buffers.

- **Uniform clamp-and-slide scenario** ($F_z = 100\text{ N}, F_x = 40\text{ N}$):
  ```powershell
  python pyqt_live.py --scenario clamp-slider --peak-force-n 100 --tangential-force-n 40 --tangential-axis x --taxel-shape circle --pitch-x-mm 25 --pitch-y-mm 25 --taxel-width-x-mm 20 --taxel-width-y-mm 20
  ```

- **Custom grid geometry** ($2 \times 4$ array, rectangular elements, 40 Hz):
  ```powershell
  python pyqt_live.py --rows 2 --cols 4 --pitch-x-mm 30 --pitch-y-mm 25 --taxel-width-x-mm 20 --taxel-width-y-mm 15 --hz 40
  ```

- **Continuous Cloud Map Mode**:
  Toggle between discrete cells and interpolated Gaussian field maps via GUI buttons, or launch directly in cloud view:
  ```powershell
  python pyqt_live.py --view cloud --cloud-channel mz
  ```
  Channels: `fz`, `shear` ($|\text{shear}|$), `mx`, `my`, `mz`. Colour ranges support `--cloud-scale auto` (fast attack with 2 s exponential half-life decay) and `--cloud-scale fixed` (calibrated to channel ceiling).

### 2. Single-Taxel Live Viewer (`pyqt_single_taxel.py`)

Dedicated live viewer for single-point sensor calibration and dynamic testing:

```powershell
python pyqt_single_taxel.py --scenario sine-shear --peak-force-n 50 --tangential-force-n 20
```

### 3. Rerun 3D Stream & Recording (`rerun_live.py`)

Streams 3D vector fields and synchronized force/moment time series directly into the Rerun Viewer:

```powershell
# Live interactive streaming:
python rerun_live.py

# Headless recording to .rrd file without opening GUI:
python rerun_live.py --duration-s 5 --save-rrd tmp/taxel-live.rrd
```

### 4. Interactive Teaching View (`app.py`)

Matplotlib-based manual teaching tool for verifying mechanics aggregation laws:

```powershell
python app.py --rows 3 --cols 3 --pitch-x-mm 20 --pitch-y-mm 20 --force-limit-n 5
```

1. Click any taxel in the left force-field plot (selected taxel highlighted with a gold border).
2. Adjust signed $f_x, f_y, f_z$ sliders below the canvas.
3. Observe real-time updates to net force ($F_x, F_y, F_z$) and moment ($M_x, M_y, M_z$) bar charts.

---

## Coordinate & Mechanical Conventions

All entry points adhere strictly to the following physical contract:

- **Axes**: $+x$ points right across the array; $+y$ points upward; $+z$ points outward normal (right-handed frame).
- **Units**: Forces in newtons ($\text{N}$); positions internally in metres ($\text{m}$), CLI/UI parameters in millimetres ($\text{mm}$); moments in newton-metres ($\text{N}\cdot\text{m}$).
- **Moment Centre**: Moments are computed relative to the array geometric centre $r_0$.
- **Aggregation Law**:
  $$\boldsymbol{F} = \sum_i \boldsymbol{f}_i, \quad \boldsymbol{M} = \sum_i (\boldsymbol{r}_i - \boldsymbol{r}_0) \times \boldsymbol{f}_i$$
- **Nominal Geometry Default**: $3 \times 3$ array, $10\text{ mm} \times 10\text{ mm}$ taxels, $10\text{ mm} \times 10\text{ mm}$ centre pitch (nominal hardware dimensions, contiguous layout with $0\text{ mm}$ physical gap; see [DESIGN.md](DESIGN.md)).

---

## Installation & Environments

To avoid native library and binary ABI conflicts on Windows (e.g., between PyQt6/PySide6, Rerun, and older Matplotlib/NumPy combinations), use dedicated Conda environments:

### Environment 1: PyQt Real-Time Viewers (`taxel-pyqt`)
For `pyqt_live.py` and `pyqt_single_taxel.py`:
```powershell
conda create -n taxel-pyqt python=3.10 pip -y
conda run -n taxel-pyqt python -m pip install -r requirements-pyqt.txt
```

### Environment 2: Rerun 3D Streamer (`tactile-viz`)
For `rerun_live.py`:
```powershell
conda create -n tactile-viz python=3.10 pip -y
conda run -n tactile-viz python -m pip install -r requirements-live.txt
```

### Environment 3: Matplotlib Offline Tool (`taxel-mpl`, optional)
For `app.py` (requires NumPy 1.26.x compatible runtime):
```powershell
conda create -n taxel-mpl python=3.10 pip -y
conda run -n taxel-mpl python -m pip install -r requirements-mpl.txt
```

---

## Verification

Run unit test suites inside their respective target environments:

```powershell
# 1. PyQt viewer, cloud interpolation, and regression test suites:
conda run -n taxel-pyqt python -m unittest test_cloud_field test_pyqt_live test_pyqt_single_taxel test_review_regressions -v

# 2. Rerun live streaming and recording tests:
conda run -n tactile-viz python -m unittest test_rerun_live -v

# 3. Aggregation mechanics and model invariant tests:
conda run -n taxel-mpl python -m unittest test_model -v
```

Tests verify mechanics aggregation laws (centred/off-centre normal loads, tangential moment arms, pure torsional shear couples), geometry limits, age-bounded monotonic history tracking, arrow orientations, and headless figure updates.

---

## Caveats & Scope Boundaries

- **Discrete Force Field**: The array visualizes discrete point forces concentrated at taxel centres. It does not perform continuous traction field reconstruction, nor does it model elastomeric cover compliance or mechanical cross-talk.
- **No Local Taxel Torque**: Individual sensing elements measure 3-axis force $[f_x, f_y, f_z]$ only without local torsional measurement; moments arise solely from spatial lever arms.
- **Cloud Smoothing Artifacts**: The cloud map interpolates Gaussian-weighted scalar distributions ($\sigma = 0.55 \times \text{pitch}$) purely for visual estimation; edge-loaded cells may visually cluster maxima near footprint boundaries.
- **Hardware Integration**: For physical sensor streaming contracts (UDP frames, `.npz` playback, sensor coordinate calibration, and replacing `live_source.py`), see [INTEGRATION.md](INTEGRATION.md).
- **Architecture & Design History**: Technical design decisions and historical changelogs are documented in [DESIGN.md](DESIGN.md) and [CHANGE_NOTICE_2026-09-22.md](CHANGE_NOTICE_2026-09-22.md).
