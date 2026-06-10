// Plotly figure builders. Plotly is loaded globally from vendor/plotly.min.js (window.Plotly).
// Each function calls Plotly.react on a target div id.

import { firstClampTime } from "./routing.js?v=14195630";

export const FNI = {
  blue: "#015D91",
  green: "#A9C945",
  navy: "#093D5E",
  orange: "#E05126",
  gray: "#4D4D4F",
};

const BASE_LAYOUT = {
  template: "plotly_white",
  margin: { l: 55, r: 20, t: 40, b: 45 },
  paper_bgcolor: "white",
  plot_bgcolor: "white",
  font: { family: "Arial, sans-serif", color: FNI.navy },
  legend: { orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1 },
};
const CONFIG = { displayModeBar: false, responsive: true };

function layout(extra) {
  return Object.assign({}, BASE_LAYOUT, extra);
}

/** Concept act: inflow vs. routed (modified) outflow. */
export function drawConcept(div, result) {
  const traces = [
    {
      x: result.timeMin, y: result.inflowCfs, mode: "lines", name: "Inflow",
      line: { color: FNI.blue, width: 3 },
    },
    {
      x: result.timeMin, y: result.modifiedOutflowCfs, mode: "lines", name: "Routed outflow",
      line: { color: FNI.green, width: 3 },
    },
  ];
  window.Plotly.react(div, traces, layout({
    xaxis: { title: "Time (minutes)" },
    yaxis: { title: "Flow (cfs)", rangemode: "tozero" },
  }), CONFIG);
}

/** Result act: inflow, base outflow, modified outflow, with a clamp marker if needed. */
export function drawResultHydro(div, result) {
  const traces = [
    { x: result.timeMin, y: result.inflowCfs, mode: "lines", name: "Inflow", line: { color: FNI.blue, width: 3 } },
    { x: result.timeMin, y: result.outflowCfs, mode: "lines", name: "Outflow", line: { color: FNI.navy, width: 3 } },
    { x: result.timeMin, y: result.modifiedOutflowCfs, mode: "lines", name: "Modified outflow", line: { color: FNI.green, width: 3 } },
  ];
  const lay = layout({
    xaxis: { title: "Time (minutes)" },
    yaxis: { title: "Flow (cfs)", rangemode: "tozero" },
  });
  const ct = firstClampTime(result);
  if (ct !== null) {
    lay.shapes = [{ type: "line", x0: ct, x1: ct, yref: "paper", y0: 0, y1: 1, line: { color: FNI.orange, width: 2, dash: "dash" } }];
    lay.annotations = [{ x: ct, yref: "paper", y: 1, text: "curve exceeded", showarrow: false, font: { color: FNI.orange, size: 11 }, yanchor: "bottom" }];
  }
  window.Plotly.react(div, traces, lay, CONFIG);
}

/** Storage-discharge curve: original vs. modified (storage x multiplier). */
export function drawCurve(div, curve, multiplier) {
  const traces = [
    {
      x: curve.storageAcft, y: curve.dischargeCfs, mode: "lines+markers", name: "Original curve",
      line: { color: FNI.blue, width: 3 }, marker: { size: 6 },
    },
    {
      x: curve.storageAcft.map((s) => s * multiplier), y: curve.dischargeCfs, mode: "lines+markers",
      name: `Modified (storage x ${multiplier.toFixed(2)})`, line: { color: FNI.green, width: 3 }, marker: { size: 6 },
    },
  ];
  window.Plotly.react(div, traces, layout({
    xaxis: { title: "Storage (acre-ft)", rangemode: "tozero" },
    yaxis: { title: "Discharge (cfs)", rangemode: "tozero" },
  }), CONFIG);
}

/**
 * Mechanics act: the storage-indication curve (x = 2S/dt + O, y = O) with a marker at the
 * current step. Axes are fixed to the curve's own range so the marker never runs off-frame.
 */
export function drawMechCurve(div, steps, k) {
  const row = steps.rows[k];
  const xmax = steps.indication[steps.indication.length - 1];
  const ymax = steps.discharge[steps.discharge.length - 1];
  const traces = [
    {
      x: steps.indication, y: steps.discharge, mode: "lines+markers", name: "Storage-indication curve",
      line: { color: FNI.blue, width: 3 }, marker: { size: 5 },
    },
    {
      x: [row.marker.x], y: [row.marker.y], mode: "markers", name: "This step",
      marker: { size: 15, color: FNI.green, line: { color: FNI.navy, width: 2 } },
    },
  ];
  const lay = layout({
    xaxis: { title: "2S/Δt + O  (cfs)", range: [0, xmax * 1.05], rangemode: "tozero" },
    yaxis: { title: "Outflow O (cfs)", range: [0, ymax * 1.05], rangemode: "tozero" },
    showlegend: false,
  });
  // Guide lines from the axes to the marker.
  lay.shapes = [
    { type: "line", x0: row.marker.x, x1: row.marker.x, y0: 0, y1: row.marker.y, line: { color: FNI.green, width: 1, dash: "dot" } },
    { type: "line", x0: 0, x1: row.marker.x, y0: row.marker.y, y1: row.marker.y, line: { color: FNI.green, width: 1, dash: "dot" } },
  ];
  window.Plotly.react(div, traces, lay, CONFIG);
}

export function resize(div) {
  if (window.Plotly && document.getElementById(div)) window.Plotly.Plots.resize(div);
}
