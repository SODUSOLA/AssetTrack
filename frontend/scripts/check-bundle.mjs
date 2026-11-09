// Fails when the built app grows past its size budget (gzipped bytes), so a heavy dependency is
// noticed in review, not by the people waiting for the page on a slow connection.
import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join, resolve } from "node:path";

const assets = resolve(import.meta.dirname, "../../backend/app/static/assets");

// Budgets are about 15% above the size when set (2026-11-02, see docs/FRONTEND.md).
const BUDGET = {
  entry: 130 * 1024, // the script every page loads (React, router, data layer)
  largestOther: 42 * 1024, // any other single script
  totalJs: 262 * 1024,
  totalCss: 14 * 1024,
};

const gz = (file) => gzipSync(readFileSync(join(assets, file))).length;
const files = readdirSync(assets);
const js = files.filter((f) => f.endsWith(".js")).map((f) => ({ f, size: gz(f) }));
const css = files.filter((f) => f.endsWith(".css")).map((f) => ({ f, size: gz(f) }));

const entry = js.find((x) => x.f.startsWith("index-"));
const others = js.filter((x) => x !== entry);
const sum = (list) => list.reduce((n, x) => n + x.size, 0);
const kb = (n) => `${(n / 1024).toFixed(1)} kB`;

const checks = [
  ["entry script", entry?.size ?? 0, BUDGET.entry],
  ["largest other script", Math.max(0, ...others.map((x) => x.size)), BUDGET.largestOther],
  ["all scripts", sum(js), BUDGET.totalJs],
  ["all styles", sum(css), BUDGET.totalCss],
];

let failed = false;
for (const [name, size, limit] of checks) {
  const ok = size <= limit;
  failed ||= !ok;
  console.log(`${ok ? "ok  " : "OVER"} ${name.padEnd(22)} ${kb(size).padStart(9)} / ${kb(limit)}`);
}
if (failed) {
  console.error(
    "\nThe app is over its size budget. Find what grew (npm run build, then compare), or raise the budget on purpose.",
  );
  process.exit(1);
}
