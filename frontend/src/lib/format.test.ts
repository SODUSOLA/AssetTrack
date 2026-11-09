import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatDateOnly,
  formatDateTime,
  formatRelative,
  initials,
  lagosMonth,
  lagosToday,
  plural,
} from "./format";

describe("dates are shown in Lagos time", () => {
  it("formats an instant in Africa/Lagos (UTC+1)", () => {
    expect(formatDateTime("2026-10-05T11:30:00Z")).toBe("05 Oct 2026, 12:30");
  });

  it("rolls into the next Lagos day when UTC is still the day before", () => {
    expect(formatDate("2026-10-05T23:30:00Z")).toBe("06 Oct 2026");
    expect(lagosToday(new Date("2026-10-05T23:30:00Z"))).toBe("2026-10-06");
  });

  it("finds the Lagos month at a month boundary", () => {
    expect(lagosMonth(new Date("2026-09-30T23:30:00Z"))).toBe("2026-10");
  });

  it("does not shift a calendar date", () => {
    expect(formatDateOnly("2026-10-05")).toBe("05 Oct 2026");
  });

  it("returns an empty string for missing values", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDateOnly(undefined)).toBe("");
  });
});

describe("small helpers", () => {
  it("pluralises", () => {
    expect(plural(1, "day")).toBe("1 day");
    expect(plural(3, "day")).toBe("3 days");
  });

  it("takes initials from first and last name", () => {
    expect(initials("Funmilayo Adeyemi")).toBe("FA");
    expect(initials("  Ngozi  ")).toBe("N");
    expect(initials("Ada Bola Chukwu")).toBe("AC");
  });

  it("describes elapsed time", () => {
    const now = new Date("2026-10-05T12:00:00Z");
    expect(formatRelative("2026-10-02T12:00:00Z", now)).toBe("3 days ago");
    expect(formatRelative("2026-10-04T12:00:00Z", now)).toBe("yesterday");
    expect(formatRelative("2026-10-05T10:00:00Z", now)).toBe("2 hours ago");
    expect(formatRelative("2026-10-05T11:59:30Z", now)).toBe("just now");
  });
});
