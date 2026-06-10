# Modified Puls Routing — Teaching Companion (static web app)

A static, client-side version of the Modified Puls routing tool, built to run entirely in the browser
and deploy to **GitHub Pages**. It teaches storage-indication routing as a three-act arc —
**Concept → Mechanics → Result** — and is meant to be opened by students on their own laptops during a
presentation.

This is the web companion to the Python/Dash app in `../modified_puls/`. That Dash app remains the
**reference implementation** and the **test oracle**: the JS routing here is a direct port, verified
against golden values exported from it.

## Run locally

No build step. Serve the folder with any static server, e.g.:

```bash
# from this directory
python -m http.server 8060
# open http://127.0.0.1:8060/
```

(Opening `index.html` via `file://` will not work — ES modules require http://.)

## Test (numeric parity with the Python core)

```bash
# 1) export golden values from the Python reference core (needs NumPy >= 2.0)
python ../../scripts/export_golden.py
# 2) run the JS parity test (Node 18+)
node --test test/routing.test.mjs
```

## Regenerate embedded presets

Presets (including the Silver Creek 100-yr data in `data/`) are embedded in `js/presets.js`:

```bash
python ../../scripts/build_presets.py
```

## Deploy to GitHub Pages

```bash
python ../../scripts/build_docs.py     # publishes index.html + css/js/vendor into ../../docs/
```

Then in the GitHub repo: **Settings → Pages → Build and deployment → Deploy from a branch**, branch =
your default branch, folder = **/docs**. The site appears at `https://<user>.github.io/<repo>/`.

## Files

| File | Purpose |
|---|---|
| `index.html` | App shell: app bar, 3 tabs, left input rail, three act panels |
| `js/routing.js` | Pure routing math (port of the Python core); has no DOM dependencies |
| `js/steps.js` | Per-step storage-indication tableau + curve-marker coordinates |
| `js/csv.js` | CSV parse + validation (BOM-stripping; mirrors the Python loaders) |
| `js/presets.js` | Auto-generated embedded teaching examples |
| `js/charts.js` | Plotly figure builders (Plotly is vendored in `vendor/`) |
| `js/app.js` | State, rail/tab/stepper wiring, URL-hash classroom sync |
| `test/` | Node parity test + golden values |
| `data/` | Provenance copies of the Silver Creek source CSVs |
