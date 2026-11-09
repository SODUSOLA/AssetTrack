import { formatDateOnly, formatDateTime } from "@/lib/format";

export type ReportKey =
  "monthly-activity" | "open-tickets" | "turnaround" | "repeat-faults" | "awaiting-unit";

/** Which controls a report needs; the page shows exactly these. */
export type ParamKind = "month" | "range" | "min" | "recent";

export type ReportDef = {
  key: ReportKey;
  label: string;
  question: string;
  params: ParamKind[];
};

export const REPORTS: ReportDef[] = [
  {
    key: "monthly-activity",
    label: "Monthly activity",
    question: "What happened to repairs this month, per unit and per device.",
    params: ["month"],
  },
  {
    key: "open-tickets",
    label: "Open tickets",
    question: "The backlog now, by unit, priority and age.",
    params: [],
  },
  {
    key: "turnaround",
    label: "Turnaround",
    question: "How long repairs take, from intake to return.",
    params: ["range"],
  },
  {
    key: "repeat-faults",
    label: "Repeat faults",
    question: "Devices that keep coming back for repair.",
    params: ["range", "min"],
  },
  {
    key: "awaiting-unit",
    label: "Waiting for units",
    question: "Overdue acknowledgements, unanswered disputes and tickets nobody confirmed.",
    params: ["recent"],
  },
];

export function isReportKey(value: string | null | undefined): value is ReportKey {
  return REPORTS.some((report) => report.key === value);
}

export type ReportParams = {
  month?: string;
  from?: string;
  to?: string;
  min?: number;
  include_recent?: boolean;
  unit_id?: string;
};

export const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

/** The query a report sends: only what that report accepts, and nothing empty. */
export function queryFor(
  key: ReportKey,
  params: ReportParams,
): Record<string, string | number | boolean> {
  const def = REPORTS.find((report) => report.key === key)!;
  const query: Record<string, string | number | boolean> = {};
  if (params.unit_id) query.unit_id = params.unit_id;
  if (def.params.includes("month") && params.month) query.month = params.month;
  if (def.params.includes("range")) {
    if (params.from) query.from = params.from;
    if (params.to) query.to = params.to;
  }
  if (def.params.includes("min") && params.min) query.min = params.min;
  if (def.params.includes("recent") && params.include_recent) query.include_recent = true;
  return query;
}

const number = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const integer = new Intl.NumberFormat("en-GB");

/** One cell, formatted by the column's declared type. Empty values show as a dash. */
export function formatCell(value: unknown, type: string): string {
  if (value === null || value === undefined || value === "") return "-";
  switch (type) {
    case "int":
      return typeof value === "number" ? integer.format(value) : String(value);
    case "number":
      return typeof value === "number" ? number.format(value) : String(value);
    case "date":
      return formatDateOnly(String(value));
    case "datetime":
      return formatDateTime(String(value));
    default:
      return String(value);
  }
}

export const isNumeric = (type: string) => type === "int" || type === "number";

/** Day figures that are measured, not counted: always one decimal, so "3.0" does not become "3". */
const MEASURED_DAYS = /^(avg|median|shortest|longest)_days$/;

/** A summary figure. Summary items carry no type, so the known measured ones are recognised by key. */
export function formatFigure(value: number | string | null, key = ""): string {
  if (value === null) return "-";
  if (typeof value === "string") return value;
  if (MEASURED_DAYS.test(key)) return number.format(value);
  return Number.isInteger(value) ? integer.format(value) : number.format(value);
}

/** "monthly-activity-2026-10.xlsx": the file's name says what it is without opening it. */
export function fileName(key: ReportKey, params: ReportParams, format: "xlsx" | "pdf"): string {
  const def = REPORTS.find((report) => report.key === key)!;
  const parts: string[] = [key];
  if (def.params.includes("month") && params.month) parts.push(params.month);
  if (def.params.includes("range") && (params.from || params.to)) {
    parts.push(`${params.from ?? "start"}_to_${params.to ?? "today"}`);
  }
  return `${parts.join("-")}.${format}`;
}
