import { useId, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import s from "./Panel.module.css";

/** A bordered region with a heading. Flat on the page, like a ruled section of a ledger. */
export function Panel({
  title,
  actions,
  children,
  className,
  flush = false,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Remove the body padding, for tables that run edge to edge. */
  flush?: boolean;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cx(s.panel, className)}>
      <header className={s.header}>
        <h2 id={id} className={s.title}>
          {title}
        </h2>
        {actions && <div className={s.actions}>{actions}</div>}
      </header>
      <div className={flush ? s.flush : s.body}>{children}</div>
    </section>
  );
}
