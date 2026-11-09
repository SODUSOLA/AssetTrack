import type { User } from "@/api/types";

/**
 * What the interface offers each role. These checks only decide which buttons to show; the API
 * enforces every permission itself, and a hidden button is never a security boundary.
 */
const isStaff = (user: User) => user.role === "admin" || user.role === "engineer";

export const can = {
  registerDevice: isStaff,
  editDevice: isStaff,
  logEvent: isStaff,
  /** Reps raise for their own unit; staff raise on a unit's behalf. Auditors only read. */
  raiseComplaint: (user: User) => user.role !== "auditor",
  /** Only a rep of the event's own unit may answer it. */
  acknowledge: (user: User, eventUnitId: string | null | undefined) =>
    user.role === "unit_rep" && !!eventUnitId && user.unit_id === eventUnitId,
  /** Unit reps only ever see their own unit, so a unit filter would be meaningless. */
  filterByUnit: (user: User) => user.role !== "unit_rep",
  manageUsers: (user: User) => user.role === "admin",
};
