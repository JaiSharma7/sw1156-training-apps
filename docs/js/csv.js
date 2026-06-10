// CSV parsing + validation for uploaded files. Mirrors the validation rules in the Python
// loaders (apps/modified_puls/app.py): constant time step, strictly increasing storage,
// monotonic nondecreasing discharge, >= 2 valid rows. Strips a leading UTF-8 BOM.

function normalizeName(name) {
  let s = String(name).trim().toLowerCase();
  for (const ch of ["(", ")", "[", "]", "{", "}"]) s = s.split(ch).join(" ");
  const parts = s.replace(/_/g, " ").split(/\s+/).filter(Boolean);
  return parts.length ? parts[0] : s;
}

function parseTable(text) {
  // Strip a leading UTF-8 BOM (pandas does this transparently; we must do it explicitly).
  const clean = text.replace(/^﻿/, "");
  const lines = clean.split(/\r?\n/).filter((ln) => ln.trim().length > 0);
  if (lines.length < 2) throw new Error("File appears to be empty.");
  const header = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1).map((ln) => ln.split(",").map((c) => c.trim()));
  return { header, rows };
}

function columnIndex(header, target) {
  const idx = header.findIndex((h) => normalizeName(h) === target);
  if (idx < 0) {
    throw new Error(`Required column '${target}' was not found. Expected a header like '${target} (...)'.`);
  }
  return idx;
}

function toNumberColumns(rows, iA, iB) {
  const a = [];
  const b = [];
  for (const r of rows) {
    const va = Number(r[iA]);
    const vb = Number(r[iB]);
    if (Number.isFinite(va) && Number.isFinite(vb)) {
      a.push(va);
      b.push(vb);
    }
  }
  return [a, b];
}

export function parseHydrograph(text) {
  const { header, rows } = parseTable(text);
  const it = columnIndex(header, "time");
  const ii = columnIndex(header, "inflow");
  const [timeMin, inflowCfs] = toNumberColumns(rows, it, ii);

  if (timeMin.length < 2) throw new Error("Hydrograph must contain at least two valid rows.");
  const dt = [];
  for (let i = 1; i < timeMin.length; i++) {
    const d = timeMin[i] - timeMin[i - 1];
    if (d <= 0) throw new Error("Hydrograph time values must be strictly increasing.");
    dt.push(d);
  }
  for (const d of dt) {
    if (Math.abs(d - dt[0]) > 1e-9) {
      throw new Error("Hydrograph time step must be constant for this app.");
    }
  }
  return { timeMin, inflowCfs };
}

export function parseStorageDischarge(text) {
  const { header, rows } = parseTable(text);
  const is = columnIndex(header, "storage");
  const id = columnIndex(header, "discharge");
  const [storageAcft, dischargeCfs] = toNumberColumns(rows, is, id);

  if (storageAcft.length < 2) {
    throw new Error("Storage-discharge curve must contain at least two valid rows.");
  }
  for (let i = 1; i < storageAcft.length; i++) {
    if (storageAcft[i] - storageAcft[i - 1] <= 0) {
      throw new Error("Storage values must be strictly increasing.");
    }
    if (dischargeCfs[i] - dischargeCfs[i - 1] < 0) {
      throw new Error("Discharge values must be monotonic nondecreasing.");
    }
  }
  return { storageAcft, dischargeCfs };
}

/** Serialize a preset/curve back to CSV text for the download buttons. */
export function hydrographToCsv(hydro) {
  const lines = ["Time (min),Inflow (cfs)"];
  for (let i = 0; i < hydro.timeMin.length; i++) lines.push(`${hydro.timeMin[i]},${hydro.inflowCfs[i]}`);
  return lines.join("\n") + "\n";
}

export function storageDischargeToCsv(curve) {
  const lines = ["Storage (acre-ft),Discharge (cfs)"];
  for (let i = 0; i < curve.storageAcft.length; i++) {
    lines.push(`${curve.storageAcft[i]},${curve.dischargeCfs[i]}`);
  }
  return lines.join("\n") + "\n";
}
