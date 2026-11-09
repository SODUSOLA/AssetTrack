import type { ComponentProps, ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { cx } from "@/lib/cx";
import s from "./Button.module.css";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "quiet" | "danger";
type Size = "md" | "sm";

type ButtonProps = ComponentProps<"button"> & {
  variant?: Variant;
  size?: Size;
  /** Disables the button and shows progress, which also prevents a double submit. */
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(s.button, s[variant], s[size], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner size="sm" /> : icon}
      {children}
    </button>
  );
}

type ButtonLinkProps = LinkProps & { variant?: Variant; size?: Size; icon?: ReactNode };

/** A link that looks like a button, for navigation that is not an action. */
export function ButtonLink({
  variant = "secondary",
  size = "md",
  icon,
  children,
  className,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link className={cx(s.button, s[variant], s[size], className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

type IconButtonProps = Omit<ComponentProps<"button">, "children" | "aria-label"> & {
  label: string;
  icon: ReactNode;
};

/** Icon only, so the accessible name is mandatory. */
export function IconButton({ label, icon, className, type = "button", ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(s.iconButton, className)}
      {...rest}
    >
      {icon}
    </button>
  );
}
