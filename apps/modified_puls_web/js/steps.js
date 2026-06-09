// Per-step routing detail for the Mechanics act: builds the storage-indication tableau and the
// marker coordinates on the indication curve, reusing the same math as routing.js.
//
// Routing is always computed at full resolution (exact numbers). For long events, the stepper only
// *displays* a capped set of representative steps — always including the first step, the inflow peak,
// and the last step — so a 865-step hydrograph doesn't require 864 clicks. Each displayed row is a
// real routed timestep; nothing about the arithmetic is approximated.

import { buildIndication, interp, ACREFT_TO_FT3 } from "./routing.js";

export const MAX_MECH_STEPS = 15;

export function buildSteps(hydro, curve) {
  const timeMin = hydro.timeMin;
  const inflow = hydro.inflowCfs;
  const storage = curve.storageAcft;
  const discharge = curve.dischargeCfs;

  const dtMin = timeMin[1] - timeMin[0];
  const dtSeconds = dtMin * 60.0;
  const indication = buildIndication(storage, discharge, dtMin);
  const lo = indication[0];
  const hi = indication[indication.length - 1];

  const n = timeMin.length;
  const outflow = new Array(n);
  const stor = new Array(n);
  outflow[0] = discharge[0];
  stor[0] = storage[0];
  let peakIdx = 0;

  // Full-resolution routing (exact); also track the inflow-peak index.
  for (let i = 1; i < n; i++) {
    const s1Ft3 = stor[i - 1] * ACREFT_TO_FT3;
    const rhs = inflow[i - 1] + inflow[i] + (2.0 * s1Ft3) / dtSeconds - outflow[i - 1];
    outflow[i] = interp(rhs, indication, discharge);
    stor[i] = interp(rhs, indication, storage);
    if (inflow[i] > inflow[peakIdx]) peakIdx = i;
  }

  // Choose which timesteps to display, capped at MAX_MECH_STEPS.
  let indices;
  if (n <= MAX_MECH_STEPS) {
    indices = Array.from({ length: n }, (_, i) => i);
  } else {
    const set = new Set([0, peakIdx, n - 1]);
    const stride = (n - 1) / (MAX_MECH_STEPS - 1);
    for (let j = 0; j < MAX_MECH_STEPS; j++) set.add(Math.round(j * stride));
    indices = [...set].sort((a, b) => a - b);
  }

  const buildRow = (i) => {
    if (i === 0) {
      return {
        idx: 0,
        tMin: timeMin[0],
        inflowSum: null,
        rhs: null,
        outflowCfs: outflow[0],
        storageAcft: stor[0],
        clamped: false,
        marker: { x: indication[0], y: discharge[0] },
      };
    }
    const s1Ft3 = stor[i - 1] * ACREFT_TO_FT3;
    const inflowSum = inflow[i - 1] + inflow[i];
    const rhs = inflowSum + (2.0 * s1Ft3) / dtSeconds - outflow[i - 1];
    const clamped = rhs < lo - 1e-9 || rhs > hi + 1e-9;
    return {
      idx: i,
      tMin: timeMin[i],
      i1: inflow[i - 1],
      i2: inflow[i],
      inflowSum,
      prevTermRhs: (2.0 * s1Ft3) / dtSeconds - outflow[i - 1], // (2S1/dt - O1)
      rhs,
      outflowCfs: outflow[i],
      storageAcft: stor[i],
      clamped,
      marker: { x: Math.min(Math.max(rhs, lo), hi), y: outflow[i] },
    };
  };

  return {
    indication,
    discharge,
    storage,
    dtMin,
    rows: indices.map(buildRow),
    totalSteps: n,
    sampled: n > MAX_MECH_STEPS,
  };
}
