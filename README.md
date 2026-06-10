# Engineering Training Apps

A suite of small, focused interactive engineering training apps for hydrology and hydraulics instruction.

The apps are intentionally lightweight Dash prototypes. Each app teaches one concept through simple inputs, immediate recalculation, side-by-side visual comparison, and concise summary metrics.

## Current apps

| App | Purpose | Run command |
|---|---|---|
| Modified Puls Routing Explorer | Demonstrates storage-discharge routing and storage sensitivity. | `python apps/modified_puls/app.py` |
| Alternatives Analysis Explorer | Compares stormwater alternatives by problem type, benefit, cost, and practicality. | `python apps/alternatives_analysis/app.py` |
| TC and Lag Assumption Explorer | Shows how lag assumptions affect runoff hydrograph shape and timing. | `python apps/tc_lag/app.py` |
| Routing Reach Representation Trainer | Shows sensitivity of Muskingum-Cunge-style routing to representative reach geometry. | `python apps/muskingum_cunge/app.py` |
| Modified Puls Teaching Companion (web) | Static, browser-only version for GitHub Pages: a guided concept → mechanics → result walkthrough of storage-indication routing. | `python -m http.server 8060 -d apps/modified_puls_web` |

## Web teaching companion (GitHub Pages)

`apps/modified_puls_web/` is a static, client-side version of the Modified Puls tool built to run
entirely in the browser and deploy to **GitHub Pages** — no Python server. It teaches storage-indication
routing as a guided **concept → mechanics → result** walkthrough and is meant for students to follow on
their own laptops during a presentation. It shares the Python core's math: `apps/modified_puls/app.py`
is the reference implementation, and a Node parity test asserts the JS output against golden values
exported from it.

Run locally (static, no build step):

```bash
python -m http.server 8060 -d apps/modified_puls_web
# open http://127.0.0.1:8060/
```

Test JS↔Python parity:

```bash
python scripts/export_golden.py                          # needs NumPy >= 2.0
node --test apps/modified_puls_web/test/routing.test.mjs
```

Publish to GitHub Pages, then enable Pages on the `/docs` folder:

```bash
python scripts/build_docs.py     # copies the app into /docs (Settings → Pages → Deploy from a branch → /docs)
```

See `apps/modified_puls_web/README.md` for the full file map and deploy notes.

## Repository goals

- Keep each teaching app focused on one learning objective.
- Separate engineering logic, validation, plotting, and UI wiring as much as practical.
- Keep early prototypes readable and easy to inspect.
- Use consistent visual standards, layout patterns, and file organization.
- Make collaboration easy through clear run instructions and lightweight contribution rules.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python apps/modified_puls/app.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python apps\modified_puls\app.py
```

Dash will print a local URL, typically `http://127.0.0.1:8050/`.

## Recommended development workflow

1. Create or update a branch for the app or change.
2. Run the affected app locally.
3. Keep calculation changes separate from UI-only changes when practical.
4. Add or update the app README when behavior, assumptions, or inputs change.
5. Open a pull request and describe what changed, how it was checked, and any known limitations.

## Standard app structure

Each app currently lives in its own folder:

```text
apps/
  modified_puls/
    app.py
    README.md
  alternatives_analysis/
    app.py
    README.md
  tc_lag/
    app.py
    README.md
  muskingum_cunge/
    app.py
    README.md
```

Inside each script, keep this section order where possible:

1. Imports
2. Constants and styles
3. Data classes
4. Helper utilities
5. Data loading and validation
6. Model computation
7. Summary metrics
8. Plotting
9. Sample data
10. App layout
11. Callbacks
12. Entry point

## NumPy integration note

Use `np.trapezoid(...)` for trapezoidal integration. NumPy 2.x removed `np.trapz`, so new code should not add new `np.trapz` calls. Where backward compatibility is needed, use a small wrapper that tries `np.trapezoid` first.

## Documentation

- `specs/` holds design specs for larger features (e.g. `specs/2026-06-08-modified-puls-teaching-companion-design.md`).
- `docs/` is the published **GitHub Pages** site — it serves the static Modified Puls Teaching Companion, built from `apps/modified_puls_web/` by `python scripts/build_docs.py`. Do not hand-edit `docs/`; edit the source and re-run the build.
- Each app keeps its own `readme.md` with its learning objective, inputs, assumptions, and outputs.

## Status

This repository is a scaffolded collaboration-ready version of the current prototype collection. The apps are runnable as single-file Dash apps. The next refactor step is to move common styling, parsing, and plotting helpers into shared modules only after repeated patterns stabilize.
