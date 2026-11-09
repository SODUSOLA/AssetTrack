import type { ComplaintDetail, ComplaintOut, User } from "@/api/types";

/**
 * What a person is offered on a complaint. The API sends no list of allowed moves, so this
 * follows the documented status flow (docs/COMPLAINTS.md). It only decides which buttons to
 * show; the server checks every move and answers a mistake with a 409 that the page explains.
 */
export type ComplaintActions = {
  assign: boolean;
  /** Admin may name anyone; an engineer may only take it themselves (they cannot list users). */
  assignAnyone: boolean;
  prioritise: boolean;
  resolve: boolean;
  close: boolean;
  confirm: boolean;
  reopen: boolean;
  comment: boolean;
};

const NONE: ComplaintActions = {
  assign: false,
  assignAnyone: false,
  prioritise: false,
  resolve: false,
  close: false,
  confirm: false,
  reopen: false,
  comment: false,
};

const isStaff = (user: User) => user.role === "admin" || user.role === "engineer";

/** A device came back for this ticket and its unit has not yet answered for it. */
export function awaitsDeviceAnswer(complaint: ComplaintDetail): boolean {
  return complaint.events.some(
    (event) => event.event_type === "returned_to_unit" && event.ack_state === "pending",
  );
}

export function complaintActions(user: User, complaint: ComplaintOut): ComplaintActions {
  const { status } = complaint;
  if (isStaff(user)) {
    const active = status === "open" || status === "in_progress" || status === "reopened";
    return {
      ...NONE,
      assign: active,
      assignAnyone: user.role === "admin",
      prioritise: active,
      resolve: status === "in_progress",
      close: status === "open" || status === "in_progress",
      reopen: status === "resolved",
      comment: true,
    };
  }
  if (user.role === "unit_rep" && user.unit_id === complaint.unit.id) {
    return {
      ...NONE,
      confirm: status === "resolved",
      reopen: status === "resolved",
      comment: true,
    };
  }
  return NONE;
}

/** The order a ticket normally moves through, for the progress strip. */
export const STATUS_STEPS = ["open", "in_progress", "resolved", "closed"] as const;
