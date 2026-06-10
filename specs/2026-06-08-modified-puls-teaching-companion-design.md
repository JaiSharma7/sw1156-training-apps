# Modified Puls Teaching Companion — Design Spec

**Date:** 2026-06-08
**Status:** Approved for planning
**Author:** brainstorming session (stormwater + software)

> Spec location note: the GitHub Pages site is published from `/docs` (see §10), so design specs live
> in the repo-root `specs/` directory rather than the skill default `docs/superpowers/specs/`, to keep
> the published site clean. This is a deliberate per-project override.

## 1. Context

The repository `sw1156-training-apps` contains four single-file **Dash** (Python, server-side)
teaching apps for hydrology/hydraulics. The Modified Puls app routes an inflow hydrograph through a
storage-discharge curve using the storage-indication (level-pool) method.

The instructor wants a tool to use **in tandem with a slide presentation** to demonstrate the Modified
Puls method **without** software like HEC-HMS — specifically one that **students follow on their own
laptops** in real time. The delivery target is **GitHub Pages**, which is static hosting and **cannot
run a Dash/Python server**. Therefore the companion must be a **static, client-side** app that performs
all routing math in the browser.

## 2. Goals / Non-Goals

**Goals**
- A static, client-side web app deployable to GitHub Pages with no server and no build step.
- Teach the method as a **three-act arc**: Concept → Mechanics → Result.
- Make the **hidden storage-indication arithmetic** visible (the part HEC-HMS hides), tied to the
  storage-indication curve geometry.
- Be **self-explanatory and robust** for a laptop audience, and **classroom-syncable** (shareable URL
  that lands everyone on the same example and step).
- Guarantee numeric correctness via parity with the existing validated Python implementation.

**Non-Goals (YAGNI)**
- No framework, no bundler, no backend, no accounts/auth.
- No scored "lab"/grading; students explore, they are not graded.
- No changes to the other three apps (`alternatives_analysis`, `tc_lag`, `muskingum_cunge`).
- The Dash `modified_puls` app is **not** deleted or modified (see §5).
- No mobile-phone layout target (laptop viewports only).

## 3. Users & Usage

- **Primary:** students following along on laptops during a live presentation, at their own pace.
- **Secondary:** the instructor, who shares a URL so the room lands on the same example/step.
- **Tertiary:** self-paced review after the talk.

Usage flow: instructor narrates slides; students open the Pages URL; the instructor can paste a
"share this view" link to sync everyone to a specific preset/multiplier/act/step.

## 4. Architecture Decision

**Plain static site, no build step** (chosen over Vite+framework and Pyodide):
- Single `index.html`; vanilla **ES-module** JavaScript; **Plotly.js** for charts, **vendored locally**
  so the app works offline (classroom wifi is unreliable).
- No toolchain, no GitHub Actions. Published by GitHub Pages "deploy from branch → `/docs`".
- Rationale: must "just work" on ~30 laptops (possibly offline), stay editable by non-frontend
  maintainers, and deploy with zero infrastructure. The routing is ~30 lines of arithmetic, so a
  WASM Python runtime (Pyodide, 6 MB+) or a full build pipeline is unjustified.

## 5. Relationship to Existing Code (Integration, No Overwrite)

- The new app is **additive**: source lives in a new sibling directory `apps/modified_puls_web/`.
  Nothing in `apps/modified_puls/` (the Dash app) is moved, overwritten, or deleted.
- The Dash `apps/modified_puls/app.py` is retained as:
  1. the **reference implementation** the JS port mirrors,
  2. the **test oracle** — golden values for the JS parity test are generated from the Python core,
  3. the **offline/desktop twin** (full-fidelity local version).
- The Python functions to mirror in JS (same equations, same behavior):
  `build_indication_curve`, `modified_puls_route` (incl. the per-step clamp mask),
  `route_both_cases`, `first_clamp_time`, `peak_stats`, `attenuation_and_lag`, `volume_acft`,
  `continuity_summary`, and the CSV validation rules in `load_hydrograph_from_df` /
  `load_storage_discharge_from_df`.
- `apps/modified_puls/test_routing.py` (pytest) remains the source of truth for expected numbers.
- The Muskingum sample-download button added earlier is unrelated and stays as-is.

## 6. Repository Layout

```
apps/modified_puls_web/          # SOURCE (single source of truth)
  index.html                     # app bar + tab stepper + left rail mount points
  css/styles.css                 # FNI theme (reuse #015D91 / #A9C945 / #093D5E ...)
  js/routing.js                  # pure routing math (port of the Python core)
  js/csv.js                      # CSV parse + validation (mirrors Python loaders)
  js/presets.js                  # built-in teaching examples as embedded data (see §7.6/§9)
  js/charts.js                   # Plotly figures + the synced mechanics marker
  js/steps.js                    # 3-act stepper + per-step tableau state
  js/app.js                      # app state, left-rail wiring, URL-hash sync
  vendor/plotly.min.js           # vendored Plotly for offline use
  data/                          # provenance copies of preset source CSVs (not published)
  test/routing.test.mjs          # Node parity test vs Python-generated golden values
  test/golden.json               # expected outputs exported from the Python core
  README.md                      # run/deploy/edit notes
scripts/export_golden.py         # runs the Python core -> writes test/golden.json
scripts/build_docs.py            # publishes the app into docs/ (copy semantics in §10)
specs/                           # design specs (this file) — NOT published by Pages
docs/                            # PUBLISHED site GitHub Pages serves (app only)
  index.html  css/  js/  vendor/ # copied from apps/modified_puls_web/ by build_docs.py
```

`docs/` contains **only** the published app (index.html, css/, js/, vendor/). Specs, tests, data, and
scripts stay in source directories and are never copied into `docs/`, so nothing internal is published.

### 6.1 Units contract (must match Python exactly for parity)
- Time is in **minutes**; the constant step `dtMin` is derived as `timeMin[1] - timeMin[0]`.
- Internally `dtSeconds = dtMin * 60.0`.
- Storage is in **acre-ft**; `1 acre-ft = 43560 ft³`.
- Storage-indication value: `O + 2 * (S_acft * 43560) / dtSeconds` (discharge in cfs).
- The JS port must replicate the `*60.0` and `*43560` conversions verbatim; these are the most likely
  source of numeric drift.
- Source CSVs may carry a leading UTF-8 BOM on the header line (the Silver Creek files do). `csv.js`
  must strip a leading BOM before header normalization (pandas does this transparently; JS must do it
  explicitly) or the first column will fail to match `time`/`storage`.

## 7. UX Design

### 7.1 Shell — guided stepper (chosen layout "A")
- Top app bar: title + a 3-tab stepper: **1 · Concept**, **2 · Mechanics**, **3 · Result**.
- A persistent **left input rail** shared across all three acts so one example carries through:
  preset dropdown, storage-multiplier slider, two CSV uploads (hydrograph, storage-discharge),
  Δt readout (auto-detected), and a **"Share this view"** button.
- The active act renders in the main panel; tabs switch acts without losing inputs.

### 7.2 Act 1 · Concept
- One plot: inflow vs. routed outflow for the current example.
- Plain-language captions defining **attenuation** (peak reduction) and **lag** (time shift).
- The storage-multiplier slider lets students *feel* "more storage → more attenuation and lag"
  before seeing any arithmetic.

### 7.3 Act 2 · Mechanics (centerpiece; chosen view "C")
- **Split view:** a compact routing **tableau** on the left (columns: t, I₁+I₂, 2S/Δt+O, O, S) and
  the **storage-indication curve** on the right.
- **Step controls:** Prev / Next / Auto-play, with a "Step k of N" counter. Stepping advances the
  active tableau row and moves a marker on the curve.
- An **equation strip** shows the Modified Puls equation with the actual numbers substituted for the
  current step, then the interpolated O₂ and S₂.
- The marker lands on the curve **within the plot axes** — axes auto-scale to the data range; the
  marker and curve never run off the frame (explicit requirement).
- Caption reinforces: "the curve *is* the routing; HEC-HMS just runs this loop for you."

### 7.4 Act 3 · Result
- Inflow / outflow / modified-outflow hydrographs (modified = storage × multiplier).
- Summary table: peak value, time of peak, **attenuation (%)**, **lag (min)** per series.
- **Volume-balance / continuity** readout (V_in, V_out, ΔS, residual %), serving as a visible
  correctness check (~0%).
- Storage-discharge curves (original vs. modified) and a **clamp annotation** when an event outgrows
  the curve (non-fatal; mirrors the Dash app's graceful-clamp behavior).

### 7.5 Presets (teaching hook)
- 3 built-in examples chosen to **contrast** behavior:
  1. "Small pond — little attenuation",
  2. "Large flat basin — strong attenuation",
  3. "Silver Creek 100-yr" — the instructor's real data (see §7.6).
- Plus upload-your-own for both inputs.

### 7.6 Silver Creek preset data (provenance)
The Silver Creek preset is built from the instructor's two CSVs, currently **outside the repo** at
`…/2026 Spring Semester/inflow_Silver_Ck_J020_blw_EX_100YR_2020.csv` (hydrograph: `Time (min)`,
`Inflow (cfs)`, 865 rows, 5-min step) and `…/2026 Spring Semester/SVSQ_Silver_Ck_R020_EX.csv`
(storage-discharge: `Storage (acre-ft)`, `Discharge (cfs)`, 15 rows). Implementation copies these into
`apps/modified_puls_web/data/` for provenance and embeds them as plain data in `js/presets.js` (so the
preset works offline with no fetch). Golden values for this case are generated from the embedded data
via the Python core (§9). This requirement is deliverable only once those files are copied into the
repo as the first implementation step.

### 7.7 Classroom sync — URL state
- The URL hash encodes: preset id, storage multiplier, active act, and step index.
- On load, the app restores that state. "Share this view" copies the current URL to the clipboard.
- **Malformed or stale hash** (unknown preset id, out-of-range multiplier/act/step) falls back to
  documented defaults silently (default preset, multiplier 1.0, Act 1, step 0) — mirroring the core's
  non-fatal philosophy. No error is shown.
- Uploaded (non-preset) data is **not** encoded in the URL (size); sharing applies to preset-based
  views. A clear note states this limitation in the UI.

## 8. Module Design (interfaces)

Each JS module is independently understandable and unit-testable.

- **`routing.js`** — pure functions, no DOM:
  - `buildIndication(storageAcft[], dischargeCfs[], dtMin) -> indication[]`
  - `route(timeMin[], inflowCfs[], storageAcft[], dischargeCfs[]) -> {outflow[], storage[], clamped[]}`
    — derives `dtMin = timeMin[1] - timeMin[0]` internally (same as the Python core); does not take Δt.
  - `routeBothCases(hydro, curve, multiplier) -> RoutingResult`
  - `volumeAcft(flowCfs[], timeMin[]) -> number`
  - `attenuationAndLag(timeMin[], inflow[], outflow[]) -> {attenuationPct, lagMin}`
  - `continuitySummary(result) -> {vIn, vOut, deltaS, residual, residualPct}`
  - `firstClampTime(result) -> number | null`
  - Behavior matches the Python core exactly, including endpoint clamping and the
    strictly-increasing-indication guard.
- **`RoutingResult` (object shape)** — the central data object three modules consume:
  `{ timeMin[], inflowCfs[], outflowCfs[], storageAcft[], modifiedOutflowCfs[],
     modifiedStorageAcft[], clampedBase[](bool), clampedModified[](bool) }`
  (mirrors the eight fields of the Python `RoutingResult` dataclass).
- **`csv.js`** — `parseHydrograph(text)` / `parseStorageDischarge(text)` returning validated arrays or
  a typed error; same rules as the Python loaders (constant Δt, strictly increasing storage, monotonic
  discharge, ≥2 rows). No external CSV dependency required for these simple two-column files.
- **`presets.js`** — exports the built-in examples as plain data objects
  `{ id, label, hydro: {timeMin[], inflowCfs[]}, curve: {storageAcft[], dischargeCfs[]} }`.
- **`charts.js`** — builds Plotly figure specs: `hydrographFigure(result)`,
  `storageDischargeFigure(curve, multiplier)`, `mechanicsFigure(curve, stepState)` (curve + in-bounds
  marker). Pure spec builders; the caller does `Plotly.react`.
- **`steps.js`** — owns mechanics step state for the base case:
  - `total(result) -> N`, `next()`, `prev()`, `goto(k)`.
  - `rowFor(k) -> { tMin, inflowSum, indicationRhs, outflowCfs, storageAcft, marker:{x,y} }`
    — the contract between `steps.js` and the Mechanics view (tableau row + equation substitution +
    curve marker coordinates). This is the most novel (non-ported) logic and is unit-tested.
- **`app.js`** — initializes state from the URL hash, wires the left rail and tabs, calls
  routing + charts on change, and writes state back to the hash. The only DOM-aware orchestrator.

## 9. Correctness & Testing

- **Golden values:** `scripts/export_golden.py` (requires NumPy ≥ 2.0, since the core uses
  `np.trapezoid`) runs the Python core and writes
  `apps/modified_puls_web/test/golden.json` for a set of cases: sample data at multipliers
  0.5/1.0/2.0/3.0; an undersized curve that clamps; and the **Silver Creek** case (using the embedded
  preset data from §7.6). This ties the JS to the already-passing pytest suite.
- **Parity test:** `test/routing.test.mjs` (Node, `node --test`) loads `golden.json` and asserts the
  JS `routing.js` outputs match within a tight tolerance (1e-6 relative), including the clamp mask and
  continuity residual.
- **`steps.js` unit test:** assert `rowFor(k)` produces the expected tableau row and marker for a known
  case (this logic is not ported, so it needs its own coverage).
- **In-app check:** the Act 3 continuity residual is displayed as a live, student-visible correctness
  indicator (~0%).
- **Manual UX checks:** stepper navigation, preset switching, upload override, URL share/restore
  (including a malformed hash falling back to defaults), offline load (disconnect wifi), and rendering
  on a typical laptop viewport.

## 10. Deployment

- GitHub Pages: "deploy from branch", folder **`/docs`**.
- `scripts/build_docs.py` publishes the app with **mirror semantics** for the app subtrees:
  - Deletes and recreates `docs/css/`, `docs/js/`, `docs/vendor/` from the source (so renamed/removed
    files do not leave stale copies), and overwrites `docs/index.html`.
  - Touches **nothing else** in `docs/` (it does not create or remove unrelated files; in this design
    `docs/` holds only the app, so there is nothing else to preserve).
  - Run before each deploy/commit.
- Plotly.js is vendored under `vendor/` (committed) so the published site has no external runtime
  dependency and works offline.
- README updates: a top-level pointer to the live URL and the one-time Pages setup; a note in
  `apps/modified_puls/readme.md` cross-linking the web companion.
- `.superpowers/` added to `.gitignore` (brainstorming scratch dir).
- `.gitignore` ignores `*.csv` globally, so a negation (`!apps/modified_puls_web/data/*.csv`) is added
  so the Silver Creek provenance CSVs can be committed. The canonical preset data is embedded in
  `presets.js` regardless; `data/` is provenance only.

## 11. Risks & Mitigations

- **Numeric drift between JS and Python** → golden-value parity test; explicit units contract (§6.1);
  Python core remains the oracle.
- **Plotly bundle size / offline** → vendor a single `plotly.min.js`; acceptable one-time load; no CDN
  dependency at runtime.
- **`/docs` publishing internal files** → `docs/` holds only the app; specs/tests/data/scripts stay in
  source dirs and are never copied.
- **URL state cannot carry uploaded data** → document clearly; sharing targets preset-based views,
  which covers the classroom-sync use case; malformed hashes fall back to defaults (§7.7).
- **Laptop viewport variety** → fluid layout with sensible min-widths; verify on common widths. Mobile
  phones are out of scope.

## 12. Verification Plan

1. `node --test apps/modified_puls_web/test/` passes (JS↔Python parity + `steps.js` unit test).
2. `python -m pytest apps/modified_puls/test_routing.py` still passes (oracle unchanged).
3. `python scripts/build_docs.py` then serve `docs/` locally (`python -m http.server`) and confirm:
   default preset renders; tabs switch; mechanics stepper advances with the marker staying in-bounds;
   clamp annotation appears on an undersized example; continuity residual ≈ 0%; "Share this view"
   round-trips via the URL hash; a hand-edited bad hash falls back to defaults; app loads with wifi
   disabled.
4. Confirm the Dash app (`python apps/modified_puls/app.py`) is unchanged and still runs.
