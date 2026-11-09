import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Button, IconButton } from "./Button";
import s from "./Dialog.module.css";

type Placement = "center" | "left";

const CONTROL = "button, a[href], input, select, textarea, summary, [tabindex]";

/**
 * The recent controls the person used (focused, or clicked: Safari and Firefox on a Mac do not
 * focus a button when it is clicked). When a dialog closes, its own controls are gone from the page,
 * so the most recent one still there is the button that opened it, or, for a dialog opened from
 * another dialog, the button in that one.
 */
const trail: HTMLElement[] = [];

function remember(event: Event): void {
  const control =
    event.target instanceof Element ? event.target.closest<HTMLElement>(CONTROL) : null;
  if (!control || trail.at(-1) === control) return;
  // Most recent last, each control once: tabbing round a long form re-touches the same controls
  // and must not push the button that opened it out of the list.
  const seen = trail.indexOf(control);
  if (seen >= 0) trail.splice(seen, 1);
  trail.push(control);
  if (trail.length > 80) trail.shift();
}

if (typeof document !== "undefined") {
  document.addEventListener("focusin", remember, true);
  document.addEventListener("click", remember, true);
}

function lastUsedControl(): HTMLElement | null {
  return [...trail].reverse().find((control) => control.isConnected) ?? null;
}

/**
 * A modal dialog (centred) or drawer (from the left). Radix supplies the focus trap, Escape,
 * focus return and aria wiring; this adds the look. Becomes full-width on phones.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  placement = "center",
  size = "md",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  placement?: Placement;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className={s.overlay} />
        <RadixDialog.Content
          className={cx(s.content, s[placement], s[size])}
          // These dialogs are opened by ordinary buttons, not Radix triggers, so Radix cannot send
          // focus back to them. Go back to the control the person was last using.
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            (lastUsedControl() ?? document.getElementById("page-title"))?.focus();
          }}
          // Radix warns about a missing description; opt out only when there really is none.
          {...(description ? {} : { "aria-describedby": undefined })}
        >
          <header className={s.header}>
            <RadixDialog.Title className={s.title}>{title}</RadixDialog.Title>
            <RadixDialog.Close asChild>
              <IconButton label="Close" icon={<X size={18} aria-hidden="true" />} />
            </RadixDialog.Close>
          </header>
          {description && (
            <RadixDialog.Description className={s.description}>
              {description}
            </RadixDialog.Description>
          )}
          <div className={s.body}>{children}</div>
          {footer && <footer className={s.footer}>{footer}</footer>}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/** Asks before something that cannot be undone. The default focus is the safe button. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "primary",
  loading = false,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "primary" | "danger";
  loading?: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button onClick={() => onOpenChange(false)} disabled={loading} autoFocus>
            {cancelLabel}
          </Button>
          <Button variant={tone} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {null}
    </Dialog>
  );
}
