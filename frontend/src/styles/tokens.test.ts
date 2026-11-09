import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "tokens.css"), "utf8");

/** The declarations inside the first block that starts with `selector {`. */
function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no block for ${selector}`);
  const end = css.indexOf("}", start);
  const out: Record<string, string> = {};
  for (const [, name, value] of css
    .slice(start, end)
    .matchAll(/(--[\w-]+):\s*([^;]+?)\s*(?:;|\/\*|$)/gm)) {
    out[name!] = value!.trim();
  }
  return out;
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const light = block(":root");
const dark = block(':root[data-theme="dark"]');
const media = (() => {
  const start = css.indexOf("@media (prefers-color-scheme: dark)");
  const open = css.indexOf("{", css.indexOf("{", start) + 1);
  return Object.fromEntries(
    [...css.slice(open, css.indexOf("}", open)).matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [
      m[1]!,
      m[2]!.trim(),
    ]),
  );
})();

/** [text, background, minimum ratio]: 4.5 for body text, 3 for large text and UI boundaries. */
const PAIRS: Array<[string, string, number]> = [
  ["--color-text", "--color-bg", 4.5],
  ["--color-text", "--color-surface", 4.5],
  ["--color-text", "--color-surface-sunken", 4.5],
  ["--color-text-secondary", "--color-surface", 4.5],
  ["--color-text-secondary", "--color-surface-sunken", 4.5],
  ["--color-text-muted", "--color-surface", 4.5],
  ["--color-text-muted", "--color-bg", 4.5],
  ["--color-on-primary", "--color-primary", 4.5],
  ["--color-on-primary", "--color-primary-hover", 4.5],
  ["--color-on-primary-soft", "--color-primary-soft", 4.5],
  ["--color-on-secondary", "--color-secondary", 4.5],
  ["--color-on-accent", "--color-accent", 4.5],
  ["--color-success", "--color-success-soft", 4.5],
  ["--color-warning", "--color-warning-soft", 4.5],
  ["--color-error", "--color-error-soft", 4.5],
  ["--color-info", "--color-info-soft", 4.5],
  ["--color-sidebar-text", "--color-sidebar", 4.5],
  ["--color-sidebar-muted", "--color-sidebar", 4.5],
  ["--color-sidebar-text", "--color-sidebar-hover", 4.5],
  ["--color-border-strong", "--color-surface", 3],
  ["--color-focus", "--color-surface", 3],
  ["--color-focus", "--color-bg", 3],
];

describe.each([
  ["light", light, light],
  ["dark", { ...light, ...dark }, { ...light, ...media }],
  ["dark (system preference)", { ...light, ...media }, { ...light, ...media }],
])("%s theme contrast", (_name, tokens) => {
  it.each(PAIRS)("%s on %s is at least %f:1", (fg, bg, minimum) => {
    const a = tokens[fg];
    const b = tokens[bg];
    expect(a, fg).toMatch(/^#[0-9a-f]{6}$/i);
    expect(b, bg).toMatch(/^#[0-9a-f]{6}$/i);
    expect(contrast(a!, b!)).toBeGreaterThanOrEqual(minimum);
  });
});

describe("dark theme", () => {
  it("is declared identically for the explicit switch and the system preference", () => {
    expect(media).toEqual(dark);
  });
});

describe("brand", () => {
  it("uses dark green, light green and yellow", () => {
    expect(light["--color-primary"]).toBe("#0f4c2f");
    expect(light["--color-secondary"]).toBe("#bfe0cc");
    expect(light["--color-accent"]).toBe("#f5b800");
  });
});
