import { z } from "zod";
import type { EventType } from "@/api/types";

/**
 * What the "log an event" form asks for, per event type. This mirrors the API's request bodies
 * (which fields exist and which are required); `eventForms.test.ts` checks it against the
 * generated OpenAPI document, so the two cannot drift apart unnoticed. Which events are allowed
 * *now* is never decided here: the server sends `allowed_events` with every device.
 */
export type FieldKind = "text" | "textarea" | "unit" | "ticket" | "event";

export type FieldSpec = {
  name: string;
  label: string;
  kind: FieldKind;
  required: boolean;
  hint?: string;
};

export type EventFormSpec = {
  /** One sentence shown under the type picker. */
  help: string;
  fields: FieldSpec[];
  /** Cannot be undone, so the form asks again before sending. */
  destructive?: boolean;
};

const notes = (label: string, required: boolean, hint?: string): FieldSpec => ({
  name: "notes",
  label,
  kind: "textarea",
  required,
  ...(hint ? { hint } : {}),
});

export const EVENT_FORMS: Partial<Record<EventType, EventFormSpec>> = {
  assigned_to_unit: {
    help: "Hand this device over to a unit. The unit is asked to confirm it received it.",
    fields: [
      { name: "unit_id", label: "Unit receiving the device", kind: "unit", required: true },
      {
        name: "counterparty_name",
        label: "Received by",
        kind: "text",
        required: true,
        hint: "The person in the unit who took it.",
      },
      notes("Notes", false),
    ],
  },
  received_for_repair: {
    help: "Take the device in for a repair. The unit is asked to confirm you received it.",
    fields: [
      {
        name: "complaint_id",
        label: "Complaint this repair is for",
        kind: "ticket",
        required: true,
      },
      {
        name: "counterparty_name",
        label: "Handed in by",
        kind: "text",
        required: true,
        hint: "The person who brought it to you.",
      },
      notes("Notes", false, "Condition of the device, accessories received."),
    ],
  },
  diagnosed: {
    help: "Record what is wrong with the device.",
    fields: [
      { name: "diagnosis", label: "What is wrong", kind: "textarea", required: true },
      notes("Notes", false),
    ],
  },
  repair_started: {
    help: "Work on the repair has begun.",
    fields: [notes("Notes", false)],
  },
  parts_requested: {
    help: "The repair is paused until parts arrive.",
    fields: [notes("Parts needed", true)],
  },
  repair_completed: {
    help: "The repair is finished. Next step: return the device to its unit.",
    fields: [notes("What was done", true)],
  },
  returned_to_unit: {
    help: "Give the repaired device back. The unit is asked to confirm, which closes the complaint.",
    fields: [
      {
        name: "counterparty_name",
        label: "Collected by",
        kind: "text",
        required: true,
        hint: "The person who took it back.",
      },
      notes("Notes", false),
    ],
  },
  decommissioned: {
    help: "Retire this device for good. It stays on record but can take no more repair steps.",
    destructive: true,
    fields: [notes("Reason", true)],
  },
  note_added: {
    help: "Add a note to the record. Use it to answer a dispute or correct an earlier entry.",
    fields: [
      notes("Note", true),
      {
        name: "corrects_event_id",
        label: "Corrects an earlier entry",
        kind: "event",
        required: false,
      },
    ],
  },
};

/** The event types to offer: what the server allows now (the system-only ones have no form). */
export function offeredEventTypes(allowed: readonly EventType[]): EventType[] {
  return allowed.filter((type) => type in EVENT_FORMS);
}

function requiredMessage(field: FieldSpec): string {
  const subject = field.label.toLowerCase();
  return field.kind === "unit" || field.kind === "ticket" || field.kind === "event"
    ? `Choose ${subject}`
    : `Enter ${subject}`;
}

export function buildEventSchema(fields: FieldSpec[]) {
  return z.object(
    Object.fromEntries(
      fields.map((field) => [
        field.name,
        field.required
          ? z
              .string()
              .trim()
              .min(1, requiredMessage(field))
              .max(2000, "Keep this under 2000 characters")
          : z.string().trim().max(2000, "Keep this under 2000 characters"),
      ]),
    ),
  );
}

/** The request body: empty optional fields are left out, and ids that are numbers become numbers. */
export function buildEventBody(type: EventType, values: Record<string, string>) {
  const body: Record<string, unknown> = { event_type: type };
  for (const [name, raw] of Object.entries(values)) {
    const value = raw.trim();
    if (value === "") continue;
    body[name] = name === "corrects_event_id" ? Number(value) : value;
  }
  return body;
}
