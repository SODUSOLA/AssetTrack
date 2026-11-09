import { describe, expect, it } from "vitest";
import type { ComplaintStatus, User } from "@/api/types";
import { COMPLAINT_ID, UNIT, complaint } from "@/test/fixtures";
import { awaitsDeviceAnswer, complaintActions } from "./rules";

const user = (role: User["role"], unit_id: string | null = null) =>
  ({ id: "u1", email: "a@b.c", full_name: "A B", role, unit_id, is_active: true }) as User;

const at = (status: ComplaintStatus) => complaint({ status });

describe("what staff may do to a complaint", () => {
  it("assigns and reprioritises while the work is still active", () => {
    for (const status of ["open", "in_progress", "reopened"] as const) {
      const a = complaintActions(user("engineer"), at(status));
      expect(a.assign, status).toBe(true);
      expect(a.prioritise, status).toBe(true);
    }
    for (const status of ["resolved", "closed"] as const) {
      const a = complaintActions(user("engineer"), at(status));
      expect(a.assign, status).toBe(false);
      expect(a.prioritise, status).toBe(false);
    }
  });

  it("resolves only work that is in progress", () => {
    expect(complaintActions(user("engineer"), at("in_progress")).resolve).toBe(true);
    expect(complaintActions(user("engineer"), at("open")).resolve).toBe(false);
    expect(complaintActions(user("engineer"), at("reopened")).resolve).toBe(false);
  });

  it("closes a duplicate or mistake only from open or in progress", () => {
    expect(complaintActions(user("admin"), at("open")).close).toBe(true);
    expect(complaintActions(user("admin"), at("in_progress")).close).toBe(true);
    expect(complaintActions(user("admin"), at("reopened")).close).toBe(false);
  });

  it("can never close a resolved complaint: only the unit can", () => {
    const a = complaintActions(user("admin"), at("resolved"));
    expect(a.close).toBe(false);
    expect(a.confirm).toBe(false);
  });

  it("lets only the head of engineering name anyone as the assignee", () => {
    expect(complaintActions(user("admin"), at("open")).assignAnyone).toBe(true);
    expect(complaintActions(user("engineer"), at("open")).assignAnyone).toBe(false);
  });
});

describe("what a unit representative may do", () => {
  const rep = user("unit_rep", UNIT.id);

  it("confirms or reopens a resolved complaint of their own unit", () => {
    const a = complaintActions(rep, at("resolved"));
    expect(a.confirm).toBe(true);
    expect(a.reopen).toBe(true);
    expect(a.comment).toBe(true);
  });

  it("cannot confirm anything that is not resolved", () => {
    for (const status of ["open", "in_progress", "reopened", "closed"] as const) {
      expect(complaintActions(rep, at(status)).confirm, status).toBe(false);
    }
  });

  it("has no engineering actions", () => {
    const a = complaintActions(rep, at("in_progress"));
    expect([a.assign, a.prioritise, a.resolve, a.close]).toEqual([false, false, false, false]);
  });

  it("is offered nothing on another unit's complaint", () => {
    const a = complaintActions(user("unit_rep", "another-unit"), at("resolved"));
    expect(Object.values(a).every((offered) => offered === false)).toBe(true);
  });
});

describe("auditors", () => {
  it("only read", () => {
    const a = complaintActions(user("auditor"), at("resolved"));
    expect(Object.values(a).every((offered) => offered === false)).toBe(true);
  });
});

describe("a returned device waiting for the unit", () => {
  const returned = (ack_state: string) =>
    complaint({
      id: COMPLAINT_ID,
      events: [{ event_type: "returned_to_unit", ack_state } as never],
    });

  it("is detected while unanswered, and not after the unit has answered", () => {
    expect(awaitsDeviceAnswer(returned("pending"))).toBe(true);
    expect(awaitsDeviceAnswer(returned("confirmed"))).toBe(false);
    expect(awaitsDeviceAnswer(complaint())).toBe(false);
  });
});
