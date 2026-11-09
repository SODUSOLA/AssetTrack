import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { API, USERS, renderApp, signInAs } from "@/test/render";

/** Pages are loaded on demand, which can take a moment on a busy machine. */
const SLOW = { timeout: 8000 };

describe("signing in", () => {
  it("sends someone who is signed out to the sign-in page, which has no accessibility violations", async () => {
    signInAs(null);
    const { container } = renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Sign in" }, SLOW)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("asks for both fields before contacting the server", async () => {
    signInAs(null);
    renderApp("/login");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }, SLOW));
    expect(await screen.findByText("Enter your email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
  });

  it("explains wrong credentials without saying which part was wrong, and clears the password", async () => {
    signInAs(null);
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json(
          { error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password" } },
          { status: 401 },
        ),
      ),
    );
    renderApp("/login");
    await userEvent.type(
      await screen.findByLabelText("Email address", undefined, SLOW),
      "head@example.test",
    );
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That email and password do not match.",
    );
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Password")).toHaveFocus();
  });

  it("signs in and returns to the page the person was heading for", async () => {
    signInAs(null);
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json({ access_token: "t", token_type: "bearer", expires_in: 1800 }),
      ),
    );
    const { router } = renderApp("/account");
    await userEvent.type(
      await screen.findByLabelText("Email address", undefined, SLOW),
      "head@example.test",
    );
    // The profile request now succeeds, as it would once the login gave a token.
    server.use(http.get(`${API}/auth/me`, () => HttpResponse.json(USERS.admin)));
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/account"));
    expect(await screen.findByRole("heading", { name: "Your account" }, SLOW)).toBeInTheDocument();
  });

  it("restores a session silently when the refresh cookie is still good", async () => {
    signInAs(USERS.admin);
    const { router } = renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Your account" }, SLOW)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/account");
  });

  it("says so when the server cannot be reached, and offers to try again", async () => {
    server.use(http.post(`${API}/auth/refresh`, () => HttpResponse.error()));
    renderApp("/");
    expect(
      await screen.findByText("The server cannot be reached", undefined, SLOW),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
