import * as Menu from "@radix-ui/react-dropdown-menu";
import { ChevronsUpDown, LogOut, Monitor, Moon, Sun, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { User } from "@/api/types";
import { useAuth } from "@/features/auth/authContext";
import { initials } from "@/lib/format";
import { ROLE_LABEL } from "@/lib/labels";
import { useTheme, type Theme } from "@/lib/theme";
import s from "./UserMenu.module.css";

export function UserMenu({ user }: { user: User }) {
  const { logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();

  return (
    <Menu.Root>
      <Menu.Trigger className={s.trigger}>
        {/* The initials are drawn by CSS, so they are neither read aloud nor part of the name. */}
        <span className={s.avatar} data-initials={initials(user.full_name)} aria-hidden="true" />
        <span className={s.who}>
          <span className={s.name}>{user.full_name}</span>{" "}
          <span className={s.role}>{ROLE_LABEL[user.role]}</span>
          <span className="sr-only">. Account menu</span>
        </span>
        <ChevronsUpDown size={16} aria-hidden="true" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content className={s.content} side="top" align="start" sideOffset={8}>
          <Menu.Label className={s.label}>{user.email}</Menu.Label>
          <Menu.Item className={s.item} onSelect={() => navigate("/account")}>
            <UserRound size={16} aria-hidden="true" /> Account and password
          </Menu.Item>
          <Menu.Separator className={s.separator} />
          <Menu.Label className={s.label}>Appearance</Menu.Label>
          <Menu.RadioGroup value={theme} onValueChange={(value) => setTheme(value as Theme)}>
            <Menu.RadioItem className={s.item} value="system">
              <Monitor size={16} aria-hidden="true" /> Match this device
            </Menu.RadioItem>
            <Menu.RadioItem className={s.item} value="light">
              <Sun size={16} aria-hidden="true" /> Light
            </Menu.RadioItem>
            <Menu.RadioItem className={s.item} value="dark">
              <Moon size={16} aria-hidden="true" /> Dark
            </Menu.RadioItem>
          </Menu.RadioGroup>
          <Menu.Separator className={s.separator} />
          <Menu.Item className={s.item} onSelect={() => void logout()}>
            <LogOut size={16} aria-hidden="true" /> Sign out
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}
