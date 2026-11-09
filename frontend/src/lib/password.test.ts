import { describe, expect, it } from "vitest";
import { generatePassword } from "./password";

describe("generated starting passwords", () => {
  it("are long enough for the API and use only unambiguous characters", () => {
    for (let i = 0; i < 50; i++) {
      const password = generatePassword();
      expect(password).toHaveLength(16);
      expect(password).toMatch(/^[a-km-zA-HJ-NP-Z2-9]+$/); // no 0 O o 1 l I
    }
  });

  it("differ every time", () => {
    const seen = new Set(Array.from({ length: 200 }, () => generatePassword()));
    expect(seen.size).toBe(200);
  });

  it("draw from the browser's secure generator, not Math.random", () => {
    let calls = 0;
    const fake = {
      getRandomValues: (array: Uint8Array) => {
        calls += 1;
        array.fill(7);
        return array;
      },
    } as unknown as Crypto;
    const password = generatePassword(10, fake);
    expect(calls).toBeGreaterThan(0);
    expect(password).toHaveLength(10);
  });

  it("never uses the biased tail of the byte range", () => {
    // 255 would map unevenly onto the alphabet; a source that only gives it must not loop forever
    // producing a skewed result, so those bytes are skipped and the next batch is drawn.
    let batch = 0;
    const fake = {
      getRandomValues: (array: Uint8Array) => {
        batch += 1;
        array.fill(batch === 1 ? 255 : 0);
        return array;
      },
    } as unknown as Crypto;
    expect(generatePassword(8, fake)).toBe("aaaaaaaa");
  });
});
