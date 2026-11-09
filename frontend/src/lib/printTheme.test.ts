import { afterEach, describe, expect, it } from "vitest";
import { installPrintTheme } from "./printTheme";

const root = document.documentElement;
afterEach(() => root.removeAttribute("data-theme"));

describe("printing is always light", () => {
  it("switches to the light theme for the print and puts a dark choice back", () => {
    root.setAttribute("data-theme", "dark");
    const stop = installPrintTheme();
    window.dispatchEvent(new Event("beforeprint"));
    expect(root.getAttribute("data-theme")).toBe("light");
    window.dispatchEvent(new Event("afterprint"));
    expect(root.getAttribute("data-theme")).toBe("dark");
    stop();
  });

  it("restores 'match this device', which has no attribute at all", () => {
    const stop = installPrintTheme();
    window.dispatchEvent(new Event("beforeprint"));
    expect(root.getAttribute("data-theme")).toBe("light");
    window.dispatchEvent(new Event("afterprint"));
    expect(root.hasAttribute("data-theme")).toBe(false);
    stop();
  });

  it("does not lose the real choice if printing starts twice", () => {
    root.setAttribute("data-theme", "dark");
    const stop = installPrintTheme();
    window.dispatchEvent(new Event("beforeprint"));
    window.dispatchEvent(new Event("beforeprint"));
    window.dispatchEvent(new Event("afterprint"));
    expect(root.getAttribute("data-theme")).toBe("dark");
    stop();
  });
});
