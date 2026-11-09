import type {
  ComplaintCategory,
  ComplaintStatus,
  DeviceStatus,
  EventType,
  PriorityLevel,
  UserRole,
} from "@/api/types";

export type Tone = "neutral" | "success" | "warning" | "error" | "info";

export const DEVICE_STATUS_LABEL: Record<DeviceStatus, string> = {
  in_stock: "In stock",
  assigned: "With unit",
  received_for_repair: "Received for repair",
  diagnosed: "Diagnosed",
  in_repair: "Being repaired",
  awaiting_parts: "Awaiting parts",
  repaired: "Repaired, ready to collect",
  decommissioned: "Decommissioned",
};

/** Colour carries a hint; the label always carries the meaning. */
export const DEVICE_STATUS_TONE: Record<DeviceStatus, Tone> = {
  in_stock: "neutral",
  assigned: "success",
  received_for_repair: "warning",
  diagnosed: "warning",
  in_repair: "warning",
  awaiting_parts: "warning",
  repaired: "info",
  decommissioned: "neutral",
};

export const EVENT_LABEL: Record<EventType, string> = {
  device_registered: "Registered",
  assigned_to_unit: "Handed to unit",
  received_for_repair: "Received for repair",
  diagnosed: "Diagnosed",
  repair_started: "Repair started",
  parts_requested: "Parts requested",
  repair_completed: "Repair completed",
  returned_to_unit: "Returned to unit",
  decommissioned: "Decommissioned",
  note_added: "Note added",
};

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Head of Engineering",
  engineer: "Engineer",
  unit_rep: "Unit representative",
  auditor: "Auditor",
};

/** Suggestions for the device type field; any text is accepted. */
export const DEVICE_TYPE_SUGGESTIONS = [
  "Laptop",
  "Desktop",
  "Printer",
  "Monitor",
  "UPS",
  "Router",
  "Switch",
  "Scanner",
  "Projector",
];

export const COMPLAINT_STATUS_LABEL: Record<ComplaintStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved, waiting for the unit",
  closed: "Closed",
  reopened: "Reopened",
};

export const COMPLAINT_STATUS_TONE: Record<ComplaintStatus, Tone> = {
  open: "warning",
  in_progress: "info",
  resolved: "success",
  closed: "neutral",
  reopened: "error",
};

export const PRIORITY_LABEL: Record<PriorityLevel, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const PRIORITY_TONE: Record<PriorityLevel, Tone> = {
  low: "neutral",
  medium: "neutral",
  high: "warning",
  critical: "error",
};

export const CATEGORY_LABEL: Record<ComplaintCategory, string> = {
  hardware: "Hardware",
  software: "Software",
  network: "Network",
  other: "Other",
};
