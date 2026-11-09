import { Menu as MenuIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { IconButton } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useUser } from "@/features/auth/authContext";
import { Brand } from "./Brand";
import s from "./AppShell.module.css";
import { navFor } from "./navigation";
import { UserMenu } from "./UserMenu";

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const user = useUser();
  return (
    <nav aria-label="Main" className={s.nav}>
      <ul>
        {navFor(user.role).map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink to={to} end={end} className={s.link} onClick={onNavigate}>
              <Icon size={18} aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * The frame around every signed-in page: a sidebar on wide screens, a top bar and drawer on
 * narrow ones. Each navigation moves focus to the page title so keyboard and screen-reader
 * users start at the top of the new page.
 */
export function AppShell() {
  const user = useUser();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    document.getElementById("page-title")?.focus();
  }, [location.pathname]);

  return (
    <div className={s.shell} data-print="flat">
      <a href="#main" className={s.skip}>
        Skip to main content
      </a>

      <aside className={s.sidebar} data-print="hide">
        <Brand />
        <Nav />
        <div className={s.account}>
          <UserMenu user={user} />
        </div>
      </aside>

      <div className={s.column}>
        <header className={s.topbar} data-print="hide">
          <Brand />
          <IconButton
            label="Open menu"
            icon={<MenuIcon size={22} aria-hidden="true" />}
            className={s.menuButton}
            onClick={() => setMenuOpen(true)}
          />
        </header>
        <main id="main" tabIndex={-1} className={s.main}>
          <div className={s.content}>
            <Outlet />
          </div>
        </main>
      </div>

      <Dialog open={menuOpen} onOpenChange={setMenuOpen} title="Menu" placement="left">
        <div className={s.drawer}>
          <Nav onNavigate={() => setMenuOpen(false)} />
          <UserMenu user={user} />
        </div>
      </Dialog>
    </div>
  );
}
