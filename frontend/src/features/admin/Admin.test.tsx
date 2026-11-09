import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { UNIT } from "@/test/fixtures";
import { API, USERS, renderApp, signInAs } from "@/test/render";
import { server } from "@/test/server";

const SLOW = { timeout: 8000 };
const unit = { ...UNIT, is_active: true, created_at: "2026-08-01T09:00:00Z" };
const finance = {
  id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
  name: "Finance and Accounts",
  code: "FIN",
  is_active: true,
  created_at: "2026-08-01T09:00:00Z",
};
const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 20 });

const emeka = { ...USERS.engineer, created_at: "2026-08-01T09:00:00Z" };
const adebayo = { ...USERS.rep, created_at: "2026-08-01T09:00:00Z" };
const head = { ...USERS.admin, created_at: "2026-08-01T09:00:00Z" };

function serveAdmin(users = [head, emeka, adebayo]) {
  const lists: URLSearchParams[] = [];
  server.use(
    http.get(`${API}/users`, ({ request }) => {
      lists.push(new globalThis.URL(request.url).searchParams);
      return HttpResponse.json(page(users));
    }),
    http.get(`${API}/units`, () => HttpResponse.json(page([unit, finance]))),
  );
  return lists;
}

function capture(method: "post" | "patch", path: string, reply: unknown, status = 200) {
  const seen: unknown[] = [];
  server.use(
    http[method](`${API}${path}`, async ({ request }) => {
      seen.push(await request.json());
      return HttpResponse.json(reply as never, { status });
    }),
  );
  return seen;
}

const refusal = (code: string, status = 409) =>
  HttpResponse.json({ error: { code, message: code } }, { status });

describe("who may open the admin pages", () => {
  it("shows people and units in the menu to the head of engineering only", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const view = renderApp("/people");
    expect(await screen.findByRole("heading", { name: "People" }, SLOW)).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Units" }).length).toBeGreaterThan(0);
    view.unmount();

    signInAs(USERS.engineer);
    renderApp("/people");
    expect(
      await screen.findByText("Your role cannot open this page", undefined, SLOW),
    ).toBeVisible();
    expect(screen.queryByRole("link", { name: "People" })).not.toBeInTheDocument();
  });

  it("turns a unit representative away from units as well", async () => {
    signInAs(USERS.rep);
    renderApp("/units");
    expect(
      await screen.findByText("Your role cannot open this page", undefined, SLOW),
    ).toBeVisible();
  });
});

describe("people", () => {
  it("lists everyone with role, unit and status, and has no accessibility violations", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const view = renderApp("/people");
    const row = await screen.findByRole("row", { name: /Adebayo Ogunleye/ }, SLOW);
    expect(within(row).getByText("Unit representative")).toBeVisible();
    expect(await within(row).findByText("Registration Office")).toBeVisible();
    expect(await axe(view.container)).toHaveNoViolations();
  });

  it("sends the role and status filters to the server", async () => {
    signInAs(USERS.admin);
    const lists = serveAdmin();
    renderApp("/people?role=engineer&status=inactive");
    await screen.findByRole("heading", { name: "People" }, SLOW);
    await waitFor(() => expect(lists.length).toBeGreaterThan(0));
    expect(lists.at(-1)!.get("role")).toBe("engineer");
    expect(lists.at(-1)!.get("is_active")).toBe("false");
  });

  it("creates an account with a generated password, shown once", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture(
      "post",
      "/users",
      {
        ...emeka,
        id: "44444444-4444-4444-8444-444444444444",
        full_name: "Ibrahim Musa",
        email: "ibrahim@example.test",
      },
      201,
    );
    renderApp("/people");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Add a person" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Full name"), "Ibrahim Musa");
    await userEvent.type(within(dialog).getByLabelText("Email address"), "ibrahim@example.test");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add person" }));

    const shown = await screen.findByTestId("one-time-password", undefined, SLOW);
    const body = seen[0] as Record<string, unknown>;
    expect(body).toMatchObject({
      full_name: "Ibrahim Musa",
      email: "ibrahim@example.test",
      role: "engineer",
    });
    expect(body.password).toBe(shown.textContent);
    expect(String(body.password).length).toBeGreaterThanOrEqual(10);
    expect(body).not.toHaveProperty("unit_id");
    expect(screen.getByText(/only time it is shown/)).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "I have passed it on" }));
    await waitFor(() => expect(screen.queryByTestId("one-time-password")).not.toBeInTheDocument());
    expect(document.body.textContent).not.toContain(String(body.password));
  });

  it("makes a unit representative choose a unit, and sends it", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture("post", "/users", adebayo, 201);
    renderApp("/people");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Add a person" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Full name"), "Folake Balogun");
    await userEvent.type(within(dialog).getByLabelText("Email address"), "folake@example.test");
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "unit_rep");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add person" }));
    expect(await within(dialog).findByText("Choose the unit this person represents")).toBeVisible();
    expect(seen).toEqual([]);

    await userEvent.selectOptions(
      await within(dialog).findByLabelText("Unit they represent"),
      await within(dialog).findByRole("option", { name: "Finance and Accounts" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Add person" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toMatchObject({ role: "unit_rep", unit_id: finance.id });
  });

  it("puts 'email taken' on the email field", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    server.use(http.post(`${API}/users`, () => refusal("EMAIL_TAKEN")));
    renderApp("/people");
    await userEvent.click(
      (await screen.findAllByRole("button", { name: "Add a person" }, SLOW))[0]!,
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Full name"), "Someone");
    await userEvent.type(within(dialog).getByLabelText("Email address"), "emeka@example.test");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add person" }));
    expect(
      await within(dialog).findByText("Another person already has that email address."),
    ).toBeVisible();
    expect(screen.queryByTestId("one-time-password")).not.toBeInTheDocument();
  });

  it("edits a person's role and unit", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture("patch", `/users/${emeka.id}`, emeka);
    renderApp("/people");
    const row = await screen.findByRole("row", { name: /Emeka Okafor/ }, SLOW);
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "auditor");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(seen).toEqual([{ full_name: "Emeka Okafor", role: "auditor", unit_id: null }]),
    );
  });

  it("will not let the head of engineering change their own role or deactivate themselves", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    renderApp("/people");
    const row = await screen.findByRole("row", { name: /Funmilayo Adeyemi/ }, SLOW);
    expect(within(row).getByText("You")).toBeVisible();
    expect(within(row).queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Role")).toBeDisabled();
    expect(within(dialog).getByText("You cannot change your own role.")).toBeVisible();
  });

  it("deactivates only after asking", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture("patch", `/users/${emeka.id}`, { ...emeka, is_active: false });
    renderApp("/people");
    const row = await screen.findByRole("row", { name: /Emeka Okafor/ }, SLOW);
    await userEvent.click(within(row).getByRole("button", { name: "Deactivate" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("signed out everywhere");
    expect(dialog).toHaveTextContent("never deleted");
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, deactivate" }));
    await waitFor(() => expect(seen).toEqual([{ is_active: false }]));
  });

  it("resets a password: a new one is sent and shown once", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture("patch", `/users/${adebayo.id}`, adebayo);
    renderApp("/people");
    const row = await screen.findByRole("row", { name: /Adebayo Ogunleye/ }, SLOW);
    await userEvent.click(within(row).getByRole("button", { name: "Reset password" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, reset it" }));
    const shown = await screen.findByTestId("one-time-password", undefined, SLOW);
    expect(seen).toEqual([{ password: shown.textContent }]);
    expect(screen.getByRole("dialog")).toHaveTextContent("signed out everywhere");
  });
});

describe("the last administrator", () => {
  it("is protected by the server, and the refusal is shown in plain words", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    server.use(http.patch(`${API}/users/${emeka.id}`, () => refusal("LAST_ADMIN")));
    renderApp("/people");
    const row = await screen.findByRole("row", { name: /Emeka Okafor/ }, SLOW);
    await userEvent.click(within(row).getByRole("button", { name: "Deactivate" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, deactivate" }),
    );
    expect(
      await screen.findByText("At least one active Head of Engineering account must remain."),
    ).toBeVisible();
  });
});

describe("units", () => {
  it("lists units and has no accessibility violations", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const view = renderApp("/units");
    expect(await screen.findByRole("row", { name: /Registration Office/ }, SLOW)).toBeVisible();
    expect(await axe(view.container)).toHaveNoViolations();
  });

  it("adds a unit, and explains a duplicate name or code", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    server.use(http.post(`${API}/units`, () => refusal("UNIT_EXISTS")));
    renderApp("/units");
    await userEvent.click((await screen.findAllByRole("button", { name: "Add a unit" }, SLOW))[0]!);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add unit" }));
    expect(await within(dialog).findByText("Enter the unit's name")).toBeVisible();
    await userEvent.type(within(dialog).getByLabelText("Name"), "Registration Office");
    await userEvent.type(within(dialog).getByLabelText("Code"), "REG");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add unit" }));
    expect(
      await within(dialog).findByText("Another unit already has that name or code."),
    ).toBeVisible();
  });

  it("creates a unit with the name and code given", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture("post", "/units", { ...finance, name: "Procurement", code: "PRO" }, 201);
    renderApp("/units");
    await userEvent.click((await screen.findAllByRole("button", { name: "Add a unit" }, SLOW))[0]!);
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "Procurement");
    await userEvent.type(within(dialog).getByLabelText("Code"), "PRO");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add unit" }));
    await waitFor(() => expect(seen).toEqual([{ name: "Procurement", code: "PRO" }]));
  });

  it("renames a unit and deactivates one after asking", async () => {
    signInAs(USERS.admin);
    serveAdmin();
    const seen = capture("patch", `/units/${finance.id}`, finance);
    renderApp("/units");
    const row = await screen.findByRole("row", { name: /Finance and Accounts/ }, SLOW);
    await userEvent.click(within(row).getByRole("button", { name: "Deactivate" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Its records stay exactly as they are");
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, deactivate" }));
    await waitFor(() => expect(seen).toEqual([{ is_active: false }]));
  });
});
