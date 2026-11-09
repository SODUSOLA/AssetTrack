import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { API, USERS, renderApp, signInAs } from "@/test/render";

const SLOW = { timeout: 8000 };

const pending = {
  items: [
    {
      event_id: 45,
      event_type: "received_for_repair",
      occurred_at: "2026-10-28T11:16:00Z",
      device: {
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        asset_tag: "LAS-ENG-000002",
        device_type: "printer",
      },
      unit: { id: USERS.rep.unit_id, name: "Registration Office", code: "REG" },
      actor: { id: "e1", full_name: "Emeka Okafor" },
      counterparty_name: "Adebayo Ogunleye",
      complaint: null,
      pending_days: 3,
      overdue: true,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
};

function listPending() {
  server.use(http.get(`${API}/acknowledgements/pending`, () => HttpResponse.json(pending)));
}

describe("a unit representative's acknowledgements", () => {
  it("lists what is waiting, with no accessibility violations", async () => {
    signInAs(USERS.rep);
    listPending();
    const { container } = renderApp("/acknowledgements");
    const row = await screen.findByRole("row", { name: /LAS-ENG-000002/ }, SLOW);
    expect(within(row).getByText(/overdue/i)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("confirms after asking, and sends a confirmation with no comment", async () => {
    signInAs(USERS.rep);
    listPending();
    let sent: unknown = null;
    server.use(
      http.post(`${API}/events/45/acknowledge`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ id: 1, event_id: 45, status: "confirmed" });
      }),
    );
    renderApp("/acknowledgements");
    await userEvent.click(await screen.findByRole("button", { name: "Confirm" }, SLOW));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("LAS-ENG-000002");
    expect(dialog).toHaveTextContent("cannot change your answer");
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, confirm" }));

    await waitFor(() => expect(sent).toEqual({ status: "confirmed", comment: null }));
    expect(await screen.findByText("Confirmed")).toBeInTheDocument();
  });

  it("will not record a dispute without saying what is wrong", async () => {
    signInAs(USERS.rep);
    listPending();
    let calls = 0;
    server.use(
      http.post(`${API}/events/45/acknowledge`, () => {
        calls += 1;
        return HttpResponse.json({ id: 1 });
      }),
    );
    renderApp("/acknowledgements");
    await userEvent.click(await screen.findByRole("button", { name: "Dispute" }, SLOW));

    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /dispute/i }));
    expect(
      await within(dialog).findByText("Say what is wrong, so engineering can respond"),
    ).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it("shows the server's refusal instead of pretending it worked", async () => {
    signInAs(USERS.rep);
    listPending();
    server.use(
      http.post(`${API}/events/45/acknowledge`, () =>
        HttpResponse.json(
          { error: { code: "INTERNAL_ERROR", message: "Something went wrong" } },
          { status: 500 },
        ),
      ),
    );
    renderApp("/acknowledgements");
    await userEvent.click(await screen.findByRole("button", { name: "Confirm" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, confirm" }));
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Confirmed")).not.toBeInTheDocument();
  });
});

describe("staff looking at the same list", () => {
  it("can see what is waiting but is never offered a way to answer for a unit", async () => {
    signInAs(USERS.admin);
    listPending();
    server.use(
      http.get(`${API}/units`, () =>
        HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 }),
      ),
    );
    renderApp("/acknowledgements");
    const row = await screen.findByRole("row", { name: /LAS-ENG-000002/ }, SLOW);
    expect(within(row).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Dispute" })).not.toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "View device" })).toBeInTheDocument();
  });
});
