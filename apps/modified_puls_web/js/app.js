// Modified Puls Teaching Companion — app orchestration.
// Owns state, wires the left rail + tabs + stepper, computes routing, and keeps the URL hash in sync.

import { PRESETS, DEFAULT_PRESET_ID } from "./presets.js";
import {
  routeBothCases, peakStats, attenuationAndLag, continuitySummary, firstClampTime,
} from "./routing.js";
import { buildSteps } from "./steps.js";
import { parseHydrograph, parseStorageDischarge, hydrographToCsv, storageDischargeToCsv } from "./csv.js";
import { drawConcept, drawResultHydro, drawCurve, drawMechCurve, resize } from "./charts.js";

const PRESET_BY_ID = Object.fromEntries(PRESETS.map((p) => [p.id, p]));

const state = {
  presetId: DEFAULT_PRESET_ID,
  multiplier: 1.0,
  act: 1,
  step: 0,
  uploadedHydro: null,
  uploadedCurve: null,
};

let computed = null; // { result, steps, hydro, curve, error }

const $ = (id) => document.getElementById(id);
const fmt = (x, d = 2) => (Number.isFinite(x) ? x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—");
const fmt0 = (x) => fmt(x, 0);

// ---------- data resolution ----------
function currentHydro() {
  return state.uploadedHydro || PRESET_BY_ID[state.presetId].hydro;
}
function currentCurve() {
  return state.uploadedCurve || PRESET_BY_ID[state.presetId].curve;
}

function recompute() {
  try {
    const hydro = currentHydro();
    const curve = currentCurve();
    const result = routeBothCases(hydro, curve, state.multiplier);
    const modifiedCurve = {
      storageAcft: curve.storageAcft.map((s) => s * state.multiplier),
      dischargeCfs: curve.dischargeCfs,
    };
    const steps = buildSteps(hydro, modifiedCurve);
    if (state.step > steps.rows.length - 1) state.step = steps.rows.length - 1;
    if (state.step < 0) state.step = 0;
    computed = { result, steps, hydro, curve, error: null };
  } catch (err) {
    computed = { error: err.message || String(err) };
  }
}

// ---------- rendering ----------
function renderStatus() {
  const el = $("status");
  if (computed.error) {
    el.classList.add("error");
    el.innerHTML = `<h2>Input error</h2><p>${computed.error}</p>`;
    return;
  }
  el.classList.remove("error");
  const dt = computed.hydro.timeMin[1] - computed.hydro.timeMin[0];
  const usingUpload = state.uploadedHydro || state.uploadedCurve;
  const src = usingUpload ? "uploaded data" : `preset: ${PRESET_BY_ID[state.presetId].label}`;
  el.innerHTML = `<h2>Ready</h2><p>Routing ${src}. Detected time step Δt = ${dt} min, storage multiplier ${state.multiplier.toFixed(2)}.</p>`;
  $("dt-readout").textContent = `${dt} min`;
}

function renderConcept() {
  const { result } = computed;
  drawConcept("concept-plot", result);
  const al = attenuationAndLag(result.timeMin, result.inflowCfs, result.modifiedOutflowCfs);
  $("concept-atten").textContent = `${al.attenuationPct.toFixed(1)}%`;
  $("concept-lag").textContent = `${fmt0(al.lagMin)} min`;
  resize("concept-plot");
}

function renderMechanics() {
  const { steps } = computed;
  const k = state.step;
  // tableau
  let html = "<thead><tr><th>t (min)</th><th>I₁+I₂</th><th>2S/Δt+O</th><th>O (cfs)</th><th>S (ac-ft)</th></tr></thead><tbody>";
  steps.rows.forEach((r, i) => {
    const cls = (i === k ? "active" : "") + (r.clamped ? " clamped" : "");
    html += `<tr class="${cls.trim()}"><td>${fmt0(r.tMin)}</td><td>${r.inflowSum == null ? "—" : fmt(r.inflowSum, 1)}</td>` +
      `<td>${r.rhs == null ? "—" : fmt(r.rhs, 1)}</td><td>${fmt(r.outflowCfs, 2)}</td><td>${fmt(r.storageAcft, 2)}</td></tr>`;
  });
  html += "</tbody>";
  $("mech-table").innerHTML = html;
  const activeRow = $("mech-table").querySelector("tr.active");
  if (activeRow) activeRow.scrollIntoView({ block: "nearest" });

  // equation
  const r = steps.rows[k];
  if (k === 0) {
    $("mech-eqn").innerHTML = `<b>Initial condition</b> at t = ${fmt0(r.tMin)} min: O = <b>${fmt(r.outflowCfs, 2)} cfs</b>, S = <b>${fmt(r.storageAcft, 2)} ac-ft</b>.`;
  } else {
    $("mech-eqn").innerHTML =
      `2S₂/Δt + O₂ = (I₁ + I₂) + (2S₁/Δt − O₁) = (${fmt(r.i1, 1)} + ${fmt(r.i2, 1)}) + (${fmt(r.prevTermRhs, 1)}) = <b>${fmt(r.rhs, 1)}</b>` +
      `<br>read off the curve → O₂ = <b>${fmt(r.outflowCfs, 2)} cfs</b>, S₂ = <b>${fmt(r.storageAcft, 2)} ac-ft</b>` +
      (r.clamped ? ` <span style="color:var(--orange)">(beyond the curve — clamped)</span>` : "");
  }

  drawMechCurve("mech-curve", steps, k);
  $("step-counter").textContent = `Step ${k} of ${steps.rows.length - 1}`;
  resize("mech-curve");
}

function metricCard(title, value, sub) {
  return `<div class="title">${title}</div><div class="value">${value}</div><div class="sub">${sub}</div>`;
}

function renderResult() {
  const { result, curve } = computed;
  drawResultHydro("result-hydro", result);
  drawCurve("result-curve", curve, state.multiplier);

  const pin = peakStats(result.timeMin, result.inflowCfs);
  const pout = peakStats(result.timeMin, result.outflowCfs);
  const pmod = peakStats(result.timeMin, result.modifiedOutflowCfs);
  const alOut = attenuationAndLag(result.timeMin, result.inflowCfs, result.outflowCfs);
  const alMod = attenuationAndLag(result.timeMin, result.inflowCfs, result.modifiedOutflowCfs);
  const cont = continuitySummary(result);

  $("m-inflow").innerHTML = metricCard("Peak Inflow", `${fmt(pin.peak, 0)} cfs`, `at ${fmt0(pin.time)} min`);
  $("m-outflow").innerHTML = metricCard("Peak Outflow", `${fmt(pout.peak, 0)} cfs`, `${alOut.attenuationPct.toFixed(0)}% atten, ${fmt0(alOut.lagMin)} min lag`);
  $("m-modified").innerHTML = metricCard("Peak Modified", `${fmt(pmod.peak, 0)} cfs`, `${alMod.attenuationPct.toFixed(0)}% atten, ${fmt0(alMod.lagMin)} min lag`);
  $("m-volume").innerHTML = metricCard("Volume Balance", `${cont.residualPct >= 0 ? "+" : ""}${cont.residualPct.toFixed(2)}%`, `in ${fmt(cont.vIn, 1)} vs out ${fmt(cont.vOut, 1)} ac-ft`);

  const pstore = peakStats(result.timeMin, result.storageAcft);
  const pmstore = peakStats(result.timeMin, result.modifiedStorageAcft);
  const rows = [
    ["Inflow", pin, "—", "—"],
    ["Outflow", pout, alOut.attenuationPct.toFixed(1), fmt0(alOut.lagMin)],
    ["Modified Outflow", pmod, alMod.attenuationPct.toFixed(1), fmt0(alMod.lagMin)],
    ["Storage", pstore, "—", "—"],
    ["Modified Storage", pmstore, "—", "—"],
  ];
  let html = "<thead><tr><th>Series</th><th>Peak</th><th>Time of peak (min)</th><th>Attenuation (%)</th><th>Lag (min)</th></tr></thead><tbody>";
  for (const [name, ps, att, lag] of rows) {
    html += `<tr><td>${name}</td><td>${fmt(ps.peak, 2)}</td><td>${fmt0(ps.time)}</td><td>${att}</td><td>${lag}</td></tr>`;
  }
  html += "</tbody>";
  $("result-table").innerHTML = html;

  const ct = firstClampTime(result);
  let notes = `Continuity residual is <b>${cont.residualPct.toFixed(2)}%</b> — inflow volume equals outflow volume plus the change in storage, which is the proof the routing conserved mass.`;
  if (ct !== null) {
    notes += `<br><span class="clamp">The event reached the top of the storage-discharge curve at t = ${fmt0(ct)} min; results past that point are clamped. Extend the curve to capture the full event.</span>`;
  }
  $("result-notes").innerHTML = notes;
  resize("result-hydro");
  resize("result-curve");
}

function renderActive() {
  renderStatus();
  for (const a of [1, 2, 3]) $(`act-${a}`).hidden = a !== state.act || !!computed.error;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", Number(t.dataset.act) === state.act));
  if (computed.error) return;
  if (state.act === 1) renderConcept();
  else if (state.act === 2) renderMechanics();
  else renderResult();
}

// ---------- URL hash ----------
function writeHash() {
  const h = `#preset=${state.presetId}&mult=${state.multiplier.toFixed(2)}&act=${state.act}&step=${state.step}`;
  history.replaceState(null, "", h);
}
function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const preset = h.get("preset");
  if (preset && PRESET_BY_ID[preset]) state.presetId = preset;
  const mult = parseFloat(h.get("mult"));
  if (Number.isFinite(mult) && mult >= 0.5 && mult <= 3.0) state.multiplier = mult;
  const act = parseInt(h.get("act"), 10);
  if (act >= 1 && act <= 3) state.act = act;
  const step = parseInt(h.get("step"), 10);
  if (Number.isFinite(step) && step >= 0) state.step = step;
}

// ---------- events ----------
function refresh() {
  recompute();
  renderActive();
  writeHash();
}

function initRail() {
  const sel = $("preset-select");
  sel.innerHTML = PRESETS.map((p) => `<option value="${p.id}">${p.label}</option>`).join("");
  sel.value = state.presetId;
  $("preset-blurb").textContent = PRESET_BY_ID[state.presetId].blurb;
  $("mult-slider").value = state.multiplier;
  $("mult-out").textContent = state.multiplier.toFixed(2);

  sel.addEventListener("change", () => {
    state.presetId = sel.value;
    state.uploadedHydro = state.uploadedCurve = null;
    $("hydro-name").textContent = "Using preset hydrograph.";
    $("curve-name").textContent = "Using preset storage-discharge curve.";
    $("preset-blurb").textContent = PRESET_BY_ID[state.presetId].blurb;
    state.step = 0;
    refresh();
  });

  $("mult-slider").addEventListener("input", (e) => {
    state.multiplier = parseFloat(e.target.value);
    $("mult-out").textContent = state.multiplier.toFixed(2);
    refresh();
  });

  $("upload-hydro").addEventListener("change", (e) => handleUpload(e, true));
  $("upload-curve").addEventListener("change", (e) => handleUpload(e, false));
  $("reset-data").addEventListener("click", () => {
    state.uploadedHydro = state.uploadedCurve = null;
    $("hydro-name").textContent = "Using preset hydrograph.";
    $("curve-name").textContent = "Using preset storage-discharge curve.";
    state.step = 0;
    refresh();
  });

  $("share-btn").addEventListener("click", () => {
    writeHash();
    navigator.clipboard.writeText(location.href).then(() => {
      const note = state.uploadedHydro || state.uploadedCurve
        ? "Link copied — note: it uses the selected preset, not your uploaded file."
        : "Link copied to clipboard.";
      $("share-status").textContent = note;
      setTimeout(() => ($("share-status").textContent = ""), 4000);
    });
  });

  $("dl-hydro").addEventListener("click", (e) => { e.preventDefault(); download("hydrograph.csv", hydrographToCsv(currentHydro())); });
  $("dl-curve").addEventListener("click", (e) => { e.preventDefault(); download("storage_discharge.csv", storageDischargeToCsv(currentCurve())); });
}

function handleUpload(e, isHydro) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      if (isHydro) {
        state.uploadedHydro = parseHydrograph(reader.result);
        $("hydro-name").textContent = `Loaded: ${file.name}`;
      } else {
        state.uploadedCurve = parseStorageDischarge(reader.result);
        $("curve-name").textContent = `Loaded: ${file.name}`;
      }
      state.step = 0;
      refresh();
    } catch (err) {
      (isHydro ? $("hydro-name") : $("curve-name")).textContent = `Error: ${err.message}`;
    }
  };
  reader.readAsText(file);
}

function download(name, text) {
  const blob = new Blob([text], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

function initTabs() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => {
      state.act = Number(t.dataset.act);
      renderActive();
      writeHash();
    });
  });
  $("step-prev").addEventListener("click", () => { stopPlay(); state.step = Math.max(0, state.step - 1); renderMechanics(); writeHash(); });
  $("step-next").addEventListener("click", () => { stopPlay(); stepNext(); });
  $("step-play").addEventListener("click", togglePlay);
}

function stepNext() {
  const max = computed.steps.rows.length - 1;
  state.step = Math.min(max, state.step + 1);
  renderMechanics();
  writeHash();
}

let playTimer = null;
function togglePlay() {
  if (playTimer) return stopPlay();
  $("step-play").textContent = "⏸ Pause";
  playTimer = setInterval(() => {
    const max = computed.steps.rows.length - 1;
    if (state.step >= max) return stopPlay();
    stepNext();
  }, 350);
}
function stopPlay() {
  if (playTimer) { clearInterval(playTimer); playTimer = null; }
  $("step-play").textContent = "▶▶ Auto-play";
}

window.addEventListener("resize", () => {
  if (computed && !computed.error) {
    if (state.act === 1) resize("concept-plot");
    else if (state.act === 2) resize("mech-curve");
    else { resize("result-hydro"); resize("result-curve"); }
  }
});

// ---------- boot ----------
readHash();
initRail();
initTabs();
refresh();
