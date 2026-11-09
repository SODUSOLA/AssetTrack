import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { API, USERS, renderApp, signInAs } from "@/test/render";

const SLOW = { timeout: 8000 };
const ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const unit = { id: USERS.rep.unit_id, name: "Registration Office", code: "REG" };

const device = {
  id: ID,
  asset_tag: "LAS-ENG-000002",
  serial_number: "HP404-7731",
  device_type: "printer",
  make: "HP",
  model: "LaserJet Pro M404",
  status: "in_repair",
  acquired_on: null,
  unit,
  created_at: "2026-08-01T09:00:00Z",
  created_by: { id: USERS.admin.id, full_name: "Funmilayo Adeyemi" },
  open_complaint_count: 1,
  allowed_events: ["repair_completed", "parts_requested", "note_added"],
};

function serve(allowed: string[] = device.allowed_events) {
  server.use(
    http.get(`${API}/devices/${ID}`, () =>
      HttpResponse.json({ ...device, allowed_events: allowed }),
    ),
    http.get(`${API}/devices/${ID}/timeline`, () => HttpResponse.json({ device, events: [] })),
    http.get(`${API}/units`, () =>
      HttpResponse.json({ items: [unit], total: 1, page: 1, page_size: 100 }),
    ),
    http.get(`${API}/complaints`, () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 }),
    ),
  );
}

describe("a device's record", () => {
  it("shows the record with no accessibility violations", async () => {
    signInAs(USERS.admin);
    serve();
    const { container } = renderApp(`/devices/${ID}`);
    expect(
      await screen.findByRole("heading", { name: "LAS-ENG-000002" }, SLOW),
    ).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers staff the steps the server allows, and nothing about vendors", async () => {
    signInAs(USERS.admin);
    serve();
    renderApp(`/devices/${ID}`);
    await userEvent.click(await screen.findByRole("button", { name: "Log an event" }, SLOW));

    const dialog = await screen.findByRole("dialog");
    const choices = within(dialog)
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(choices).toContain("Repair completed");
    expect(choices.join(" ")).not.toMatch(/vendor/i);
  });

  it("gives a unit representative no way to change the record", async () => {
    signInAs(USERS.rep);
    serve();
    renderApp(`/devices/${ID}`);
    expect(
      await screen.findByRole("heading", { name: "LAS-ENG-000002" }, SLOW),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log an event" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
  });

  it("says plainly when the device is not found", async () => {
    signInAs(USERS.admin);
    server.use(
      http.get(`${API}/devices/${ID}`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", message: "Not found" } }, { status: 404 }),
      ),
      http.get(`${API}/devices/${ID}/timeline`, () =>
        HttpResponse.json({ error: { code: "NOT_FOUND", message: "Not found" } }, { status: 404 }),
      ),
    );
    renderApp(`/devices/${ID}`);
    expect(await screen.findByText("There is no such device", undefined, SLOW)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Device not found" })).toBeInTheDocument();
  });
});
