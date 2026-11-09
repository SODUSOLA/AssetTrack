import { setNonce } from "get-nonce";

/**
 * The server puts a fresh nonce in the page and in its Content-Security-Policy. The dialog and
 * menu library locks scrolling by injecting a <style> element; given the nonce, it can, and
 * the policy stays free of 'unsafe-inline'. Without a server (dev, tests) the placeholder is
 * still in the page and nothing is set.
 */
export function applyServerNonce(doc: Document = document): void {
  const nonce = doc.querySelector('meta[name="csp-nonce"]')?.getAttribute("content");
  if (nonce && !nonce.startsWith("__")) setNonce(nonce);
}
