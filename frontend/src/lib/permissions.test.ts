import { describe, expect, it } from "vitest";
import type { User } from "@/api/types";
import { can } from "./permissions";

const user = (role: User["role"], unit_id: string | null = null) =>
  ({ id: "u", email: "a@b.c", full_name: "A B", role, unit_id }) as User;

describe("what the interface offers", () => {
  it("lets the head of engineering and engineers change records", () => {
    for (const role of ["admin", "engineer"] as const) {
      expect(can.registerDevice(user(role))).toBe(true);
      expect(can.editDevice(user(role))).toBe(true);
      expect(can.logEvent(user(role))).toBe(true);
    }
  });

  it("offers auditors and unit reps no editing", () => {
    for (const role of ["auditor", "unit_rep"] as const) {
      expect(can.registerDevice(user(role, "x"))).toBe(false);
      expect(can.logEvent(user(role, "x"))).toBe(false);
    }
  });

  it("lets a rep answer only for their own unit", () => {
    const rep = user("unit_rep", "unit-1");
    expect(can.acknowledge(rep, "unit-1")).toBe(true);
    expect(can.acknowledge(rep, "unit-2")).toBe(false);
    expect(can.acknowledge(rep, null)).toBe(false);
  });

  it("never lets staff answer on a unit's behalf", () => {
    expect(can.acknowledge(user("admin"), "unit-1")).toBe(false);
    expect(can.acknowledge(user("engineer"), "unit-1")).toBe(false);
  });

  it("hides the unit filter from reps and user management from everyone but the head", () => {
    expect(can.filterByUnit(user("unit_rep", "x"))).toBe(false);
    expect(can.filterByUnit(user("auditor"))).toBe(true);
    expect(can.manageUsers(user("admin"))).toBe(true);
    expect(can.manageUsers(user("engineer"))).toBe(false);
  });
});
