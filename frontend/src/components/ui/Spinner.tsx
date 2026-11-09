import { cx } from "@/lib/cx";
import s from "./Spinner.module.css";

/** Decorative; pair it with text or `Loading` so assistive technology hears about it. */
export function Spinner({ size = "md", className }: { size?: "sm" | "md"; className?: string }) {
  return <span aria-hidden="true" className={cx(s.spinner, s[size], className)} />;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className={s.loading}>
      <Spinner />
      <span>{label}…</span>
    </div>
  );
}
