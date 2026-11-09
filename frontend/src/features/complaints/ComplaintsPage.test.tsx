import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { COMPLAINT_ID, UNIT, complaint } from "@/test/fixtures";
import { API, USERS, renderApp, signInAs } from "@/test/render";
import { server } from "@/test/server";

const SLOW = { timeout: 8000 };

const { comments: _comments, events: _events, ...row } = complaint();
const list = (items = [row]) => ({ items, total: items.length, page: 1, page_size: 20 });

/** Serve the list, remembering the query string of every request. */
function serveList(items = [row]) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get(`${API}/complaints`, ({ request }) => {
      queries.push(new globalThis.URL(request.url).searchParams);
      return HttpResponse.json(list(items));
    }),
    http.get(`${API}/units`, () =>
      HttpResponse.json({
        items: [{ ...UNIT, is_active: true }],
        total: 1,
        page: 1,
        page_size: 100,
      }),
    ),
  );
  return queries;
}

describe("the complaints list", () => {
  it("lists tickets with their status and priority, and has no accessibility violations", async () => {
    signInAs(USERS.admin);
    serveList();
    const view = renderApp("/complaints");
    const line = await screen.findByRole("row", { name: /TKT-2026-00004/ }, SLOW);
    expect(within(line).getByText("Open")).toBeInTheDocument();
    expect(within(line).getByText("Medium")).toBeInTheDocument();
    expect(within(line).getByText("Nobody yet")).toBeInTheDocument();
    expect(within(line).getByRole("link", { name: "LAS-ENG-000002" })).toBeInTheDocument();
    expect(await axe(view.container)).toHaveNoViolations();
  });

  it("asks the server for exactly the filters in the address", async () => {
    signInAs(USERS.admin);
    const queries = serveList();
    renderApp("/complaints?status=in_progress&priority=high&unit=" + UNIT.id);
    await screen.findByRole("row", { name: /TKT-2026-00004/ }, SLOW);
    const last = queries.at(-1)!;
    expect(last.get("status")).toBe("in_progress");
    expect(last.get("priority")).toBe("high");
    expect(last.get("unit_id")).toBe(UNIT.id);
  });

  it("filters to the signed-in engineer's own complaints with 'Assigned to: Me'", async () => {
    signInAs(USERS.engineer);
    const queries = serveList();
    renderApp("/complaints");
    await userEvent.selectOptions(
      await screen.findByLabelText("Assigned to", undefined, SLOW),
      "yes",
    );
    await waitFor(() => expect(queries.at(-1)!.get("assigned_to")).toBe(USERS.engineer.id));
  });

  it("shows a unit representative neither the unit filter nor an assignee filter", async () => {
    signInAs(USERS.rep);
    const queries = serveList();
    renderApp("/complaints?unit=" + "99999999-9999-4999-8999-999999999999");
    await screen.findByRole("row", { name: /TKT-2026-00004/ }, SLOW);
    expect(screen.queryByLabelText("Unit")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Assigned to")).not.toBeInTheDocument();
    // A unit typed into the address is ignored: the server scopes a rep to their own unit anyway.
    expect(queries.at(-1)!.has("unit_id")).toBe(false);
  });

  it("says when nothing matches the filters, and offers to clear them", async () => {
    signInAs(USERS.admin);
    serveList([]);
    renderApp("/complaints?status=closed");
    expect(await screen.findByText("No complaints match", undefined, SLOW)).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Clear filters" }).length).toBeGreaterThan(0);
  });

  it("explains an empty list to a rep, with a way to raise the first complaint", async () => {
    signInAs(USERS.rep);
    serveList([]);
    renderApp("/complaints");
    expect(await screen.findByText("No complaints yet", undefined, SLOW)).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Raise a complaint" }).length).toBeGreaterThan(0);
  });

  it("does not offer an auditor a way to raise complaints", async () => {
    server.use(
      http.post(`${API}/auth/refresh`, () =>
        HttpResponse.json({ access_token: "t", token_type: "bearer", expires_in: 1800 }),
      ),
      http.get(`${API}/auth/me`, () => HttpResponse.json({ ...USERS.admin, role: "auditor" })),
    );
    serveList();
    renderApp("/complaints");
    await screen.findByRole("row", { name: /TKT-2026-00004/ }, SLOW);
    expect(screen.queryByRole("button", { name: "Raise a complaint" })).not.toBeInTheDocument();
  });
});

describe("raising a complaint", () => {
  function serveRaise() {
    const bodies: unknown[] = [];
    server.use(
      http.post(`${API}/complaints`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(complaint(), { status: 201 });
      }),
      http.get(`${API}/complaints/${COMPLAINT_ID}`, () => HttpResponse.json(complaint())),
      http.get(`${API}/devices`, () =>
        HttpResponse.json({
          items: [
            {
              id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
              asset_tag: "LAS-ENG-000002",
              device_type: "printer",
              status: "assigned",
            },
            {
              id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
              asset_tag: "LAS-ENG-000009",
              device_type: "scanner",
              status: "decommissioned",
            },
          ],
          total: 2,
          page: 1,
          page_size: 100,
        }),
      ),
    );
    return bodies;
  }

  it("lets a rep raise one for their own unit, never naming the unit", async () => {
    signInAs(USERS.rep);
    serveList();
    const bodies = serveRaise();
    renderApp("/complaints");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Raise a complaint" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText("Unit this is for")).not.toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText("Title"), "Printer streaks");
    await userEvent.type(within(dialog).getByLabelText("What is wrong"), "Streaks on every page");
    await userEvent.selectOptions(
      await within(dialog).findByLabelText(/Device/),
      "LAS-ENG-000002 · printer",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Raise complaint" }));

    await waitFor(() =>
      expect(bodies).toEqual([
        {
          title: "Printer streaks",
          description: "Streaks on every page",
          category: "hardware",
          priority: "medium",
          device_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        },
      ]),
    );
    // The new complaint's page opens.
    expect(await screen.findByRole("heading", { name: "TKT-2026-00004" }, SLOW)).toBeVisible();
  });

  it("does not offer a decommissioned device", async () => {
    signInAs(USERS.rep);
    serveList();
    serveRaise();
    renderApp("/complaints");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Raise a complaint" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("option", { name: "LAS-ENG-000002 · printer" });
    expect(
      within(dialog).queryByRole("option", { name: /LAS-ENG-000009/ }),
    ).not.toBeInTheDocument();
  });

  it("asks for a title and a description before sending", async () => {
    signInAs(USERS.rep);
    serveList();
    const bodies = serveRaise();
    renderApp("/complaints");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Raise a complaint" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Raise complaint" }));
    expect(await within(dialog).findByText("Give the problem a short title")).toBeVisible();
    expect(within(dialog).getByText("Describe what is wrong")).toBeVisible();
    expect(bodies).toEqual([]);
  });

  it("makes staff choose the unit first, then sends it", async () => {
    signInAs(USERS.engineer);
    serveList();
    const bodies = serveRaise();
    renderApp("/complaints");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Raise a complaint" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Device/)).toBeDisabled();

    await userEvent.type(within(dialog).getByLabelText("Title"), "No network");
    await userEvent.type(within(dialog).getByLabelText("What is wrong"), "Cannot connect");
    await userEvent.click(within(dialog).getByRole("button", { name: "Raise complaint" }));
    expect(await within(dialog).findByText("Choose the unit this is for")).toBeVisible();
    expect(bodies).toEqual([]);

    await userEvent.selectOptions(
      await within(dialog).findByLabelText("Unit this is for"),
      await within(dialog).findByRole("option", { name: "Registration Office" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Raise complaint" }));
    await waitFor(() =>
      expect(bodies).toEqual([
        {
          title: "No network",
          description: "Cannot connect",
          category: "hardware",
          priority: "medium",
          unit_id: UNIT.id,
        },
      ]),
    );
  });

  it("has no accessibility violations", async () => {
    signInAs(USERS.rep);
    serveList();
    serveRaise();
    renderApp("/complaints");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Raise a complaint" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    expect(await axe(dialog)).toHaveNoViolations();
  });
});
