import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { PublicOnly, RequireAuth, RequireRole } from "@/features/auth/guards";
import { NotFoundPage } from "@/features/auth/StatusPages";

/** Pages load on demand, so signing in does not download the whole app. */
export const routes: RouteObject[] = [
  {
    path: "/login",
    lazy: async () => {
      const { LoginPage } = await import("@/features/auth/LoginPage");
      return {
        element: (
          <PublicOnly>
            <LoginPage />
          </PublicOnly>
        ),
      };
    },
  },
  {
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      {
        index: true,
        lazy: async () => ({
          Component: (await import("@/features/dashboard/DashboardPage")).DashboardPage,
        }),
      },
      {
        path: "devices",
        lazy: async () => ({
          Component: (await import("@/features/devices/DevicesPage")).DevicesPage,
        }),
      },
      {
        path: "devices/:deviceId",
        lazy: async () => ({
          Component: (await import("@/features/devices/DeviceDetailPage")).DeviceDetailPage,
        }),
      },
      {
        path: "complaints",
        lazy: async () => ({
          Component: (await import("@/features/complaints/ComplaintsPage")).ComplaintsPage,
        }),
      },
      {
        path: "complaints/:complaintId",
        lazy: async () => ({
          Component: (await import("@/features/complaints/ComplaintDetailPage"))
            .ComplaintDetailPage,
        }),
      },
      {
        path: "acknowledgements",
        lazy: async () => ({
          Component: (await import("@/features/acknowledgements/AcknowledgementsPage"))
            .AcknowledgementsPage,
        }),
      },
      {
        path: "reports",
        lazy: async () => ({
          Component: (await import("@/features/reports/ReportsPage")).ReportsPage,
        }),
      },
      {
        path: "people",
        lazy: async () => {
          const { UsersPage } = await import("@/features/admin/UsersPage");
          return {
            element: (
              <RequireRole roles={["admin"]}>
                <UsersPage />
              </RequireRole>
            ),
          };
        },
      },
      {
        path: "units",
        lazy: async () => {
          const { UnitsPage } = await import("@/features/admin/UnitsPage");
          return {
            element: (
              <RequireRole roles={["admin"]}>
                <UnitsPage />
              </RequireRole>
            ),
          };
        },
      },
      {
        path: "account",
        lazy: async () => ({
          Component: (await import("@/features/auth/AccountPage")).AccountPage,
        }),
      },
      { path: "*", Component: NotFoundPage },
    ],
  },
];

export const router = createBrowserRouter(routes, {
  basename: import.meta.env.BASE_URL.replace(/\/$/, ""),
});
