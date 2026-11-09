import type { ComplaintDetail, Report } from "@/api/types";
import { USERS } from "./render";

export const UNIT = { id: USERS.rep.unit_id, name: "Registration Office", code: "REG" };
export const DEVICE_REF = {
  id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  asset_tag: "LAS-ENG-000002",
  device_type: "printer",
};
export const ENGINEER = { id: "33333333-3333-4333-8333-333333333333", full_name: "Emeka Okafor" };

export const COMPLAINT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

/** A complaint as `GET /complaints/{id}` returns it; override only what a test is about. */
export function complaint(overrides: Partial<ComplaintDetail> = {}): ComplaintDetail {
  return {
    id: COMPLAINT_ID,
    ticket_no: "TKT-2026-00004",
    unit: UNIT,
    raised_by: { id: USERS.rep.id, full_name: USERS.rep.full_name },
    device: DEVICE_REF,
    category: "hardware",
    title: "Printer streaks every page",
    description: "Pages come out streaked since Monday.",
    priority: "medium",
    status: "open",
    assigned_to: null,
    created_at: "2026-10-20T09:00:00Z",
    resolved_at: null,
    closed_at: null,
    comments: [
      {
        id: 1,
        author: { id: USERS.rep.id, full_name: USERS.rep.full_name },
        body: "Priority: medium. Status: open.",
        is_system: true,
        created_at: "2026-10-20T09:00:01Z",
      },
    ],
    events: [],
    ...overrides,
  };
}

/** A report as the API returns it. */
export function report(overrides: Partial<Report> = {}): Report {
  return {
    key: "turnaround",
    title: "Repair turnaround",
    period: "03 Aug 2026 to 01 Nov 2026",
    scope: { unit_id: null, label: "All units" },
    generated_at: "2026-11-01T10:00:00Z",
    generated_by: { id: USERS.admin.id, full_name: USERS.admin.full_name },
    summary: [
      { key: "repairs", label: "Repairs returned", value: 4 },
      { key: "avg_days", label: "Average days", value: 4.5 },
    ],
    sections: [
      {
        key: "by_unit",
        title: "By unit",
        columns: [
          { key: "unit", label: "Unit", type: "text" },
          { key: "repairs", label: "Repairs returned", type: "int" },
          { key: "avg_days", label: "Average days", type: "number" },
        ],
        rows: [
          { unit: "Registration Office", repairs: 3, avg_days: 4.25 },
          { unit: "Finance and Accounts", repairs: 1, avg_days: 5 },
        ],
        totals: { unit: "All units", repairs: 4, avg_days: 4.5 },
        note: "Days from intake to return.",
      },
      {
        key: "repairs",
        title: "Repairs returned in the period",
        columns: [
          { key: "returned_at", label: "Returned", type: "datetime" },
          { key: "asset_tag", label: "Asset tag", type: "text" },
          { key: "date", label: "Date", type: "date" },
        ],
        rows: [
          {
            returned_at: "2026-10-05T14:30+01:00",
            asset_tag: "LAS-ENG-000002",
            date: "2026-10-05",
          },
        ],
        totals: null,
        note: null,
      },
    ],
    ...overrides,
  };
}
