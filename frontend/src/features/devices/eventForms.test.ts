import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { EventType } from "@/api/types";
import { EVENT_FORMS, buildEventBody, buildEventSchema, offeredEventTypes } from "./eventForms";

type Schema = { properties?: Record<string, unknown>; required?: string[] };
const spec = JSON.parse(readFileSync(resolve(__dirname, "../../../openapi.json"), "utf8")) as {
  paths: Record<
    string,
    { post?: { requestBody: { content: Record<string, { schema: unknown }> } } }
  >;
  components: { schemas: Record<string, Schema> };
};

const body = spec.paths["/api/v1/devices/{device_id}/events"]!.post!.requestBody.content[
  "application/json"
]!.schema as { discriminator: { mapping: Record<string, string> } };

const apiSchema = (type: string): Schema =>
  spec.components.schemas[body.discriminator.mapping[type]!.split("/").pop()!]!;

const eventTypes = Object.keys(body.discriminator.mapping) as EventType[];

describe("the log-event form matches the API", () => {
  it("has a form for every event type the interface offers", () => {
    const missing = eventTypes.filter((t) => !(t in EVENT_FORMS));
    expect(missing).toEqual([]);
  });

  it.each(Object.entries(EVENT_FORMS))(
    "%s asks for exactly the fields the API accepts",
    (type, form) => {
      const api = apiSchema(type);
      const accepted = Object.keys(api.properties ?? {}).filter((f) => f !== "event_type");
      const asked = form!.fields.map((f) => f.name);
      for (const name of asked) expect(accepted, `${type}.${name}`).toContain(name);
      for (const name of (api.required ?? []).filter((f) => f !== "event_type")) {
        const field = form!.fields.find((f) => f.name === name);
        expect(field?.required, `${type}.${name} must be required`).toBe(true);
      }
    },
  );
});

describe("which events are offered", () => {
  it("offers only steps that have a form, in the order the server gives them", () => {
    expect(offeredEventTypes(["note_added", "diagnosed", "device_registered"])).toEqual([
      "note_added",
      "diagnosed",
    ]);
  });

  it("knows nothing of vendors: repairs are done in-house", () => {
    expect(Object.keys(EVENT_FORMS).join(" ")).not.toMatch(/vendor/i);
    expect(eventTypes.join(" ")).not.toMatch(/vendor/i); // nor does the API
  });
});

describe("form values", () => {
  it("rejects missing required fields with plain wording", () => {
    const schema = buildEventSchema(EVENT_FORMS.diagnosed!.fields);
    const result = schema.safeParse({ fault_description: "  ", notes: "" });
    expect(result.success).toBe(false);
  });

  it("leaves empty optional fields out of the request", () => {
    expect(buildEventBody("note_added", { notes: "  hello ", extra: "" })).toEqual({
      event_type: "note_added",
      notes: "hello",
    });
  });

  it("sends a correction target as a number", () => {
    expect(buildEventBody("note_added", { notes: "x", corrects_event_id: "43" })).toMatchObject({
      corrects_event_id: 43,
    });
  });
});
