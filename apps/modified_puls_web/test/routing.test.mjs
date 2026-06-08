// Parity test: assert the JS routing matches golden values exported from the Python core.
// Run from apps/modified_puls_web:  node --test test/
// (golden.json is produced by scripts/export_golden.py)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  routeBothCases,
  firstClampTime,
  continuitySummary,
  attenuationAndLag,
} from "../js/routing.js";

const here = dirname(fileURLToPath(import.meta.url));
const golden = JSON.parse(readFileSync(join(here, "golden.json"), "utf-8"));

const REL = 1e-6;
const ABS = 1e-6;

function close(a, b, msg) {
  const diff = Math.abs(a - b);
  const tol = ABS + REL * Math.abs(b);
  assert.ok(diff <= tol, `${msg}: got ${a}, expected ${b} (diff ${diff} > tol ${tol})`);
}

function closeArray(a, b, msg) {
  assert.equal(a.length, b.length, `${msg}: length ${a.length} != ${b.length}`);
  for (let i = 0; i < a.length; i++) close(a[i], b[i], `${msg}[${i}]`);
}

for (const c of golden.cases) {
  test(`parity: ${c.id}`, () => {
    const result = routeBothCases(c.hydro, c.curve, c.multiplier);
    const e = c.expected;

    closeArray(result.outflowCfs, e.outflowCfs, "outflowCfs");
    closeArray(result.storageAcft, e.storageAcft, "storageAcft");
    closeArray(result.modifiedOutflowCfs, e.modifiedOutflowCfs, "modifiedOutflowCfs");
    closeArray(result.modifiedStorageAcft, e.modifiedStorageAcft, "modifiedStorageAcft");

    assert.deepEqual(result.clampedBase, e.clampedBase, "clampedBase mask");
    assert.deepEqual(result.clampedModified, e.clampedModified, "clampedModified mask");

    const fct = firstClampTime(result);
    assert.equal(fct, e.firstClampTime, "firstClampTime");

    const cont = continuitySummary(result);
    close(cont.vIn, e.continuity.vIn, "vIn");
    close(cont.vOut, e.continuity.vOut, "vOut");
    close(cont.deltaS, e.continuity.deltaS, "deltaS");
    close(cont.residualPct, e.continuity.residualPct, "residualPct");

    const ao = attenuationAndLag(result.timeMin, result.inflowCfs, result.outflowCfs);
    close(ao.attenuationPct, e.attenuationOutPct, "attenuationOutPct");
    close(ao.lagMin, e.lagOutMin, "lagOutMin");

    const am = attenuationAndLag(result.timeMin, result.inflowCfs, result.modifiedOutflowCfs);
    close(am.attenuationPct, e.attenuationModPct, "attenuationModPct");
    close(am.lagMin, e.lagModMin, "lagModMin");
  });
}
