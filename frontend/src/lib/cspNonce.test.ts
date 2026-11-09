import { getNonce } from "get-nonce";
import { describe, expect, it } from "vitest";
import { applyServerNonce } from "./cspNonce";

function page(content: string): Document {
  return new DOMParser().parseFromString(
    `<html><head><meta name="csp-nonce" content="${content}"></head></html>`,
    "text/html",
  );
}

describe("the server's nonce", () => {
  it("is handed to the style library when the server provided one", () => {
    applyServerNonce(page("k3J9-abc_XYZ"));
    expect(getNonce()).toBe("k3J9-abc_XYZ");
  });

  it("is ignored while it is still the placeholder (no server)", () => {
    applyServerNonce(page("k3J9-abc_XYZ"));
    applyServerNonce(page("__CSP_NONCE__"));
    expect(getNonce()).toBe("k3J9-abc_XYZ"); // the placeholder never replaces a real nonce
  });

  it("does nothing when the page has no nonce tag", () => {
    expect(() =>
      applyServerNonce(new DOMParser().parseFromString("<html></html>", "text/html")),
    ).not.toThrow();
  });
});
