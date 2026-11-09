import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { REPORTS, fileName, formatCell, formatFigure, isReportKey, queryFor } from "./reports";

const spec = JSON.parse(readFileSync(resolve(__dirname, "../../openapi.json"), "utf8")) as {
  paths: Record<string, { get: { parameters: Array<{ name: string }> } }>;
};

describe("what each report asks the API", () => {
  it.each(REPORTS)("$key sends only parameters the API accepts", ({ key }) => {
    const accepted = spec.paths[`/api/v1/reports/${key}`]!.get.parameters.map((p) => p.name);
    const everything = {
      month: "2026-10",
      from: "2026-08-01",
      to: "2026-10-31",
      min: 3,
      include_recent: true,
      unit_id: "u",
    };
    for (const name of Object.keys(queryFor(key, everything))) {
      expect(accepted, `${key}.${name}`).toContain(name);
    }
  });

  it("leaves out empty settings and settings a report does not have", () => {
    expect(queryFor("open-tickets", { month: "2026-10", from: "2026-01-01", min: 5 })).toEqual({});
    expect(queryFor("turnaround", { from: "", to: "2026-10-31", min: 9 })).toEqual({
      to: "2026-10-31",
    });
    expect(queryFor("monthly-activity", { month: "2026-10", unit_id: "u1" })).toEqual({
      month: "2026-10",
      unit_id: "u1",
    });
    expect(queryFor("awaiting-unit", { include_recent: false })).toEqual({});
  });

  it("recognises only real report names", () => {
    expect(isReportKey("turnaround")).toBe(true);
    expect(isReportKey("costs")).toBe(false);
    expect(isReportKey(null)).toBe(false);
  });
});

describe("cells", () => {
  it("formats by the column's type", () => {
    expect(formatCell(1234, "int")).toBe("1,234");
    expect(formatCell(4.25, "number")).toBe("4.3");
    expect(formatCell(5, "number")).toBe("5.0");
    expect(formatCell("2026-10-05", "date")).toBe("05 Oct 2026");
    expect(formatCell("2026-10-05T14:30+01:00", "datetime")).toBe("05 Oct 2026, 14:30");
    expect(formatCell("Registration Office", "text")).toBe("Registration Office");
  });

  it("shows a dash for nothing, but keeps a real zero", () => {
    expect(formatCell(null, "int")).toBe("-");
    expect(formatCell("", "text")).toBe("-");
    expect(formatCell(0, "int")).toBe("0");
  });

  it("formats summary figures", () => {
    expect(formatFigure(12)).toBe("12");
    expect(formatFigure(4.5)).toBe("4.5");
    expect(formatFigure(null)).toBe("-");
    expect(formatFigure(3, "avg_days")).toBe("3.0");
    expect(formatFigure(3, "oldest_days")).toBe("3");
  });
});

describe("file names", () => {
  it("say what the file is", () => {
    expect(fileName("monthly-activity", { month: "2026-10" }, "xlsx")).toBe(
      "monthly-activity-2026-10.xlsx",
    );
    expect(fileName("turnaround", { from: "2026-08-01", to: "2026-10-31" }, "pdf")).toBe(
      "turnaround-2026-08-01_to_2026-10-31.pdf",
    );
    expect(fileName("open-tickets", {}, "pdf")).toBe("open-tickets.pdf");
  });
});
