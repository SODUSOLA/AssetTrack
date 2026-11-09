import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import type { ComplaintDetail } from "@/api/types";
import { COMPLAINT_ID, ENGINEER, complaint } from "@/test/fixtures";
import { API, USERS, renderApp, signInAs } from "@/test/render";
import { server } from "@/test/server";

const SLOW = { timeout: 8000 };
const TICKET_URL = `${API}/complaints/${COMPLAINT_ID}`;

function serve(c: ComplaintDetail) {
  server.use(http.get(TICKET_URL, () => HttpResponse.json(c)));
}

/** Record the JSON body of the next request to `path`, and answer with `reply`. */
function capture(method: "patch" | "post", path: string, reply: unknown = complaint()) {
  const seen: unknown[] = [];
  server.use(
    http[method](`${API}${path}`, async ({ request }) => {
      seen.push(request.headers.get("content-type") ? await request.json() : null);
      return HttpResponse.json(reply as never);
    }),
  );
  return seen;
}

const refusal = (code: string, message: string, status = 409) =>
  HttpResponse.json({ error: { code, message } }, { status });

const open = () => renderApp(`/complaints/${COMPLAINT_ID}`);

describe("staff working a complaint", () => {
  it("shows the history and offers assignment and closing, with no accessibility violations", async () => {
    signInAs(USERS.admin);
    serve(complaint());
    const view = open();
    expect(await screen.findByRole("heading", { name: "TKT-2026-00004" }, SLOW)).toBeVisible();
    expect(screen.getByRole("button", { name: "Assign" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark resolved" })).not.toBeInTheDocument();
    expect(screen.getByText("Priority: medium. Status: open.")).toBeInTheDocument();
    expect(await axe(view.container)).toHaveNoViolations();
  });

  it("lets an engineer take a complaint for themselves, which starts the work", async () => {
    signInAs(USERS.engineer);
    serve(complaint());
    const seen = capture("patch", `/complaints/${COMPLAINT_ID}`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Take it" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Take it" }));
    await waitFor(() => expect(seen).toEqual([{ assigned_to: USERS.engineer.id }]));
  });

  it("offers an engineer nothing to take once the complaint is already theirs", async () => {
    signInAs(USERS.engineer);
    serve(complaint({ status: "in_progress", assigned_to: ENGINEER }));
    open();
    await screen.findByRole("heading", { name: "TKT-2026-00004" }, SLOW);
    expect(screen.queryByRole("button", { name: "Take it" })).not.toBeInTheDocument();
  });

  it("lets the head of engineering choose anyone from the staff list", async () => {
    signInAs(USERS.admin);
    serve(complaint());
    server.use(
      http.get(`${API}/users`, ({ request }) => {
        const role = new URL(request.url).searchParams.get("role");
        const items = role === "engineer" ? [USERS.engineer] : [USERS.admin];
        return HttpResponse.json({ items, total: items.length, page: 1, page_size: 100 });
      }),
    );
    const seen = capture("patch", `/complaints/${COMPLAINT_ID}`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Assign" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(
      await within(dialog).findByLabelText("Assign to"),
      await within(dialog).findByRole("option", { name: "Emeka Okafor" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Assign" }));
    await waitFor(() => expect(seen).toEqual([{ assigned_to: USERS.engineer.id }]));
  });

  it("will not mark a complaint resolved without saying what was done", async () => {
    signInAs(USERS.engineer);
    serve(complaint({ status: "in_progress", assigned_to: ENGINEER }));
    const seen = capture("patch", `/complaints/${COMPLAINT_ID}`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Mark resolved" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark resolved" }));
    expect(await within(dialog).findByText(/Write a note/)).toBeInTheDocument();
    expect(seen).toEqual([]);

    await userEvent.type(within(dialog).getByLabelText("What was done"), "Replaced the drum");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark resolved" }));
    await waitFor(() =>
      expect(seen).toEqual([{ status: "resolved", comment: "Replaced the drum" }]),
    );
  });

  it("explains in plain words why a complaint cannot be resolved yet", async () => {
    signInAs(USERS.engineer);
    serve(complaint({ status: "in_progress", assigned_to: ENGINEER }));
    server.use(
      http.patch(TICKET_URL, () => refusal("DEVICE_IN_REPAIR", "Device is still in repair")),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Mark resolved" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("What was done"), "Done");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark resolved" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("has not been returned yet");
  });

  it("closing as a duplicate asks for a reason and sends status closed", async () => {
    signInAs(USERS.admin);
    serve(complaint());
    const seen = capture("patch", `/complaints/${COMPLAINT_ID}`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Close" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Why it is being closed"), "Duplicate of 3");
    await userEvent.click(within(dialog).getByRole("button", { name: "Close complaint" }));
    await waitFor(() => expect(seen).toEqual([{ status: "closed", comment: "Duplicate of 3" }]));
  });

  it("changes the priority", async () => {
    signInAs(USERS.admin);
    serve(complaint());
    const seen = capture("patch", `/complaints/${COMPLAINT_ID}`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Priority" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Priority"), "critical");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(seen).toEqual([{ priority: "critical" }]));
  });
});

describe("a unit representative answering for their unit", () => {
  const resolved = () => complaint({ status: "resolved", resolved_at: "2026-10-25T10:00:00Z" });

  it("confirms after asking, which closes the complaint", async () => {
    signInAs(USERS.rep);
    serve(resolved());
    const seen = capture("post", `/complaints/${COMPLAINT_ID}/confirm`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Confirm it is fixed" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("cannot reopen a closed complaint");
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, it is fixed" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(await screen.findByText("Complaint closed")).toBeInTheDocument();
  });

  it("reopens only with a reason", async () => {
    signInAs(USERS.rep);
    serve(resolved());
    const seen = capture("post", `/complaints/${COMPLAINT_ID}/reopen`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Reopen" }, SLOW));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reopen" }));
    expect(await within(dialog).findByText(/Write a note/)).toBeInTheDocument();
    expect(seen).toEqual([]);

    await userEvent.type(within(dialog).getByLabelText("What is still wrong"), "Streaks are back");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reopen" }));
    await waitFor(() => expect(seen).toEqual([{ reason: "Streaks are back" }]));
  });

  it("is sent to the device when the returned device is still waiting for an answer", async () => {
    signInAs(USERS.rep);
    serve(
      complaint({
        status: "resolved",
        events: [{ id: 41, event_type: "returned_to_unit", ack_state: "pending" } as never],
      }),
    );
    open();
    expect(
      await screen.findByRole("link", { name: "Answer on the device" }, SLOW),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm it is fixed" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
  });

  it("has none of engineering's controls", async () => {
    signInAs(USERS.rep);
    serve(complaint({ status: "in_progress", assigned_to: ENGINEER }));
    open();
    await screen.findByRole("heading", { name: "TKT-2026-00004" }, SLOW);
    for (const name of ["Assign", "Reassign", "Take it", "Priority", "Close", "Mark resolved"]) {
      expect(screen.queryByRole("button", { name }), name).not.toBeInTheDocument();
    }
  });
});

describe("the comment thread", () => {
  it("posts a comment and clears the box", async () => {
    signInAs(USERS.rep);
    serve(complaint());
    const seen = capture("post", `/complaints/${COMPLAINT_ID}/comments`, {
      id: 2,
      author: { id: USERS.rep.id, full_name: USERS.rep.full_name },
      body: "Still streaking",
      is_system: false,
      created_at: "2026-10-21T09:00:00Z",
    });
    open();
    const box = await screen.findByLabelText("Add a comment", undefined, SLOW);
    await userEvent.type(box, "Still streaking");
    await userEvent.click(screen.getByRole("button", { name: "Post comment" }));
    await waitFor(() => expect(seen).toEqual([{ body: "Still streaking" }]));
    await waitFor(() => expect(box).toHaveValue(""));
  });

  it("will not post an empty comment", async () => {
    signInAs(USERS.rep);
    serve(complaint());
    const seen = capture("post", `/complaints/${COMPLAINT_ID}/comments`);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Post comment" }, SLOW));
    expect(await screen.findByText("Write something first")).toBeInTheDocument();
    expect(seen).toEqual([]);
  });

  it("marks system entries as recorded changes, apart from people's comments", async () => {
    signInAs(USERS.admin);
    serve(complaint());
    open();
    expect(await screen.findByText("recorded a change", undefined, SLOW)).toBeInTheDocument();
  });

  it("gives an auditor no way to comment", async () => {
    server.use(
      http.post(`${API}/auth/refresh`, () =>
        HttpResponse.json({ access_token: "t", token_type: "bearer", expires_in: 1800 }),
      ),
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json({ ...USERS.admin, role: "auditor", full_name: "Ngozi Eze" }),
      ),
    );
    serve(complaint());
    open();
    await screen.findByRole("heading", { name: "TKT-2026-00004" }, SLOW);
    expect(screen.queryByLabelText("Add a comment")).not.toBeInTheDocument();
  });
});

describe("a complaint that is not there", () => {
  it("says so plainly, whether it is missing or belongs to another unit", async () => {
    signInAs(USERS.rep);
    server.use(
      http.get(TICKET_URL, () => refusal("COMPLAINT_NOT_FOUND", "Complaint not found", 404)),
    );
    open();
    expect(await screen.findByText("There is no such complaint", undefined, SLOW)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Complaint not found" })).toBeVisible();
  });
});
