import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

type Schema = { properties?: Record<string, unknown>; required?: string[] };
const spec = JSON.parse(readFileSync(resolve(__dirname, "../../../openapi.json"), "utf8")) as {
  components: { schemas: Record<string, Schema & { enum?: string[] }> };
};
const schemas = spec.components.schemas;

/** The complaint forms send these bodies. If the API changes them, this fails before users do. */
describe("complaint requests match the API", () => {
  it("raising sends only fields the API accepts, and the required ones", () => {
    const create = schemas.ComplaintCreate!;
    for (const field of ["title", "description", "category", "priority", "device_id", "unit_id"]) {
      expect(Object.keys(create.properties ?? {}), field).toContain(field);
    }
    expect(create.required).toEqual(expect.arrayContaining(["title", "description"]));
  });

  it("offers the same categories, priorities and statuses as the API", () => {
    expect(schemas.ComplaintCategory!.enum).toEqual(["hardware", "software", "network", "other"]);
    expect(schemas.PriorityLevel!.enum).toEqual(["low", "medium", "high", "critical"]);
    expect(schemas.ComplaintStatus!.enum).toEqual([
      "open",
      "in_progress",
      "resolved",
      "closed",
      "reopened",
    ]);
  });

  it("changes a ticket with assigned_to, priority, status and comment", () => {
    expect(Object.keys(schemas.ComplaintUpdate!.properties ?? {}).sort()).toEqual([
      "assigned_to",
      "comment",
      "priority",
      "status",
    ]);
  });

  it("reopens with a reason and comments with a body", () => {
    expect(schemas.ReopenRequest!.required).toEqual(["reason"]);
    expect(schemas.CommentCreate!.required).toEqual(["body"]);
  });
});
