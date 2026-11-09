import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routes } from "@/app/routes";
import { session } from "@/api/session";
import { ToastProvider } from "@/components/ui/Toast";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { createQueryClient } from "@/lib/query";
import { server } from "./server";

export const API = "http://localhost:3000/api/v1";

export const USERS = {
  admin: {
    id: "11111111-1111-4111-8111-111111111111",
    email: "head@example.test",
    full_name: "Funmilayo Adeyemi",
    role: "admin",
    unit_id: null,
    is_active: true,
  },
  engineer: {
    id: "33333333-3333-4333-8333-333333333333",
    email: "emeka@example.test",
    full_name: "Emeka Okafor",
    role: "engineer",
    unit_id: null,
    is_active: true,
  },
  rep: {
    id: "22222222-2222-4222-8222-222222222222",
    email: "rep@example.test",
    full_name: "Adebayo Ogunleye",
    role: "unit_rep",
    unit_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    is_active: true,
  },
} as const;

/** The network as seen by someone who is signed in as `user` (or nobody). */
export function signInAs(user: (typeof USERS)[keyof typeof USERS] | null) {
  server.use(
    http.post(`${API}/auth/refresh`, () =>
      user
        ? HttpResponse.json({ access_token: "test-token", token_type: "bearer", expires_in: 1800 })
        : HttpResponse.json(
            { error: { code: "INVALID_REFRESH_TOKEN", message: "Sign in again" } },
            { status: 401 },
          ),
    ),
    http.get(`${API}/auth/me`, () =>
      user
        ? HttpResponse.json(user)
        : HttpResponse.json({ error: { code: "UNAUTHENTICATED", message: "no" } }, { status: 401 }),
    ),
  );
}

/** The whole app, at `path`, with a fresh router, cache and session. */
export function renderApp(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({
    queries: { retry: false, staleTime: 0, refetchOnWindowFocus: false },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <TooltipProvider>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...view, router, session };
}
