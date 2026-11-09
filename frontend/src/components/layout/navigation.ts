import {
  BadgeCheck,
  BarChart3,
  ClipboardList,
  Building2,
  LayoutDashboard,
  MonitorSmartphone,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { UserRole } from "@/api/types";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Match only the exact path, so "Dashboard" is not active on every page. */
  end?: boolean;
  /** Omit to show to everyone. */
  roles?: UserRole[];
};

/** Routes are added here as each part of the app ships; nothing links to a page that does not exist. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/devices", label: "Devices", icon: MonitorSmartphone },
  { to: "/complaints", label: "Complaints", icon: ClipboardList },
  { to: "/acknowledgements", label: "Acknowledgements", icon: BadgeCheck },
  { to: "/reports", label: "Reports", icon: BarChart3 },
  { to: "/people", label: "People", icon: Users, roles: ["admin"] },
  { to: "/units", label: "Units", icon: Building2, roles: ["admin"] },
];

export function navFor(role: UserRole): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));
}
