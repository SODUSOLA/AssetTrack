import { AlertCircle, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { describeError } from "@/lib/messages";
import { Button } from "./Button";
import s from "./Feedback.module.css";

type AlertTone = "error" | "warning" | "success" | "info";
const ICONS = { error: AlertCircle, warning: TriangleAlert, success: CircleCheck, info: Info };

/** An inline message. Errors are announced immediately; the rest politely. */
export function Alert({
  tone = "info",
  title,
  children,
}: {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
}) {
  const Icon = ICONS[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx(s.alert, s[tone])}>
      <Icon size={20} aria-hidden="true" className={s.alertIcon} />
      <div>
        {title && <p className={s.alertTitle}>{title}</p>}
        {children && <div>{children}</div>}
      </div>
    </div>
  );
}

/** Explains why a list is empty and what to do next. */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={s.state}>
      <h3 className={s.stateTitle}>{title}</h3>
      {description && <p className={s.stateText}>{description}</p>}
      {action && <div className={s.stateAction}>{action}</div>}
    </div>
  );
}

/** A failed load, with the reason in plain words and a way to try again. */
export function ErrorState({
  error,
  onRetry,
  title = "This could not be loaded",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div className={s.state} role="alert">
      <h3 className={s.stateTitle}>{title}</h3>
      <p className={s.stateText}>{describeError(error)}</p>
      {onRetry && (
        <div className={s.stateAction}>
          <Button onClick={onRetry}>Try again</Button>
        </div>
      )}
    </div>
  );
}
