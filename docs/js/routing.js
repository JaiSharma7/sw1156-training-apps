// Modified Puls (storage-indication / level-pool) routing — browser port of the
// Python reference implementation in apps/modified_puls/app.py.
//
// Units contract (must match the Python core exactly):
//   - time in minutes; dtMin = timeMin[1] - timeMin[0]; dtSeconds = dtMin * 60
//   - storage in acre-ft; 1 acre-ft = 43560 ft^3
//   - storage-indication value: O + 2 * (S_acft * 43560) / dtSeconds   (discharge in cfs)

export const ACREFT_TO_FT3 = 43560.0;

/**
 * NumPy-style linear interpolation that clamps to the endpoints outside [xs[0], xs[-1]].
 * `xs` must be strictly increasing.
 */
export function interp(x, xs, ys) {
  const n = xs.length;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];
  // binary search for the interval
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= x) lo = mid;
    else hi = mid;
  }
  const t = (x - xs[lo]) / (xs[hi] - xs[lo]);
  return ys[lo] + t * (ys[hi] - ys[lo]);
}

/** Trapezoidal integration of y over x (mirrors np.trapezoid). */
export function trapezoid(y, x) {
  let total = 0.0;
  for (let i = 0; i < x.length - 1; i++) {
    total += 0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i]);
  }
  return total;
}

export function buildIndication(storageAcft, dischargeCfs, dtMin) {
  const dtSeconds = dtMin * 60.0;
  return storageAcft.map((s, i) => dischargeCfs[i] + (2.0 * s * ACREFT_TO_FT3) / dtSeconds);
}

/**
 * Route an inflow hydrograph through a storage-discharge curve.
 * dtMin is derived internally as timeMin[1] - timeMin[0] (same as the Python core).
 * Returns { outflow, storage, clamped } where `clamped[i]` flags steps that left the curve range.
 */
export function route(timeMin, inflowCfs, storageAcft, dischargeCfs) {
  const dtMin = timeMin[1] - timeMin[0];
  const indication = buildIndication(storageAcft, dischargeCfs, dtMin);

  for (let i = 1; i < indication.length; i++) {
    if (indication[i] - indication[i - 1] <= 0) {
      throw new Error(
        "The storage-indication curve is not strictly increasing. Check the storage-discharge data."
      );
    }
  }

  const n = timeMin.length;
  const outflow = new Array(n).fill(0);
  const storage = new Array(n).fill(0);
  const clamped = new Array(n).fill(false);

  outflow[0] = dischargeCfs[0];
  storage[0] = storageAcft[0];

  const dtSeconds = dtMin * 60.0;
  let lo = indication[0];
  let hi = indication[0];
  for (const v of indication) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }

  for (let i = 1; i < n; i++) {
    const s1Ft3 = storage[i - 1] * ACREFT_TO_FT3;
    const rhs = inflowCfs[i - 1] + inflowCfs[i] + (2.0 * s1Ft3) / dtSeconds - outflow[i - 1];

    if (rhs < lo - 1e-9 || rhs > hi + 1e-9) clamped[i] = true;

    // interp clamps to the curve endpoints outside the provided range.
    outflow[i] = interp(rhs, indication, dischargeCfs);
    storage[i] = interp(rhs, indication, storageAcft);
  }

  return { outflow, storage, clamped };
}

/**
 * Route both the base curve and a storage-multiplied "modified" curve.
 * @returns RoutingResult — see fields below (mirrors the Python dataclass, 8 arrays).
 */
export function routeBothCases(hydro, curve, multiplier) {
  const timeMin = hydro.timeMin;
  const inflowCfs = hydro.inflowCfs;
  const storageAcft = curve.storageAcft;
  const dischargeCfs = curve.dischargeCfs;

  const base = route(timeMin, inflowCfs, storageAcft, dischargeCfs);

  const modifiedStorageCurve = storageAcft.map((s) => s * multiplier);
  const modified = route(timeMin, inflowCfs, modifiedStorageCurve, dischargeCfs);

  return {
    timeMin,
    inflowCfs,
    outflowCfs: base.outflow,
    storageAcft: base.storage,
    modifiedOutflowCfs: modified.outflow,
    modifiedStorageAcft: modified.storage,
    clampedBase: base.clamped,
    clampedModified: modified.clamped,
  };
}

/** Earliest time (minutes) at which either routed case left the provided curve, or null. */
export function firstClampTime(result) {
  const times = [];
  for (const mask of [result.clampedBase, result.clampedModified]) {
    const idx = mask.findIndex((c) => c);
    if (idx >= 0) times.push(result.timeMin[idx]);
  }
  return times.length ? Math.min(...times) : null;
}

/** Peak value and its time. */
export function peakStats(timeMin, values) {
  let idx = 0;
  for (let i = 1; i < values.length; i++) if (values[i] > values[idx]) idx = i;
  return { peak: values[idx], time: timeMin[idx] };
}

/** Peak attenuation (percent reduction) and lag (time-of-peak shift, minutes). */
export function attenuationAndLag(timeMin, inflow, outflow) {
  const pin = peakStats(timeMin, inflow);
  const pout = peakStats(timeMin, outflow);
  const attenuationPct = pin.peak ? ((pin.peak - pout.peak) / pin.peak) * 100.0 : 0.0;
  const lagMin = pout.time - pin.time;
  return { attenuationPct, lagMin };
}

/** Hydrograph volume in acre-ft (flow in cfs, time in minutes). */
export function volumeAcft(flowCfs, timeMin) {
  const timeSec = timeMin.map((t) => t * 60.0);
  return trapezoid(flowCfs, timeSec) / ACREFT_TO_FT3;
}

/**
 * Mass balance for the base case: V_in - V_out should equal the change in storage.
 * The continuity residual is what the routing did not account for and should be near zero.
 */
export function continuitySummary(result) {
  const vIn = volumeAcft(result.inflowCfs, result.timeMin);
  const vOut = volumeAcft(result.outflowCfs, result.timeMin);
  const deltaS = result.storageAcft[result.storageAcft.length - 1] - result.storageAcft[0];
  const residual = vIn - vOut - deltaS;
  const residualPct = vIn ? (residual / vIn) * 100.0 : 0.0;
  return { vIn, vOut, deltaS, residual, residualPct };
}
