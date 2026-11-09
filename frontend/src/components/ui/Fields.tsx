import { useId, type ComponentProps, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import s from "./Fields.module.css";

type FieldChrome = {
  label: string;
  hint?: ReactNode;
  error?: string | undefined;
  /** Show "(optional)" next to the label. Required fields are the default and need no mark. */
  optional?: boolean;
};

function Chrome({
  id,
  label,
  hint,
  error,
  optional,
  children,
  className,
}: FieldChrome & { id: string; children: ReactNode; className?: string | undefined }) {
  return (
    <div className={cx(s.field, className)}>
      <label htmlFor={id} className={s.label}>
        {label}
        {optional && <span className={s.optional}> (optional)</span>}
      </label>
      {hint && (
        <p id={`${id}-hint`} className={s.hint}>
          {hint}
        </p>
      )}
      {children}
      {error && (
        <p id={`${id}-error`} className={s.error}>
          {error}
        </p>
      )}
    </div>
  );
}

function describedBy(id: string, hint: ReactNode, error?: string): string | undefined {
  const ids = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

type TextFieldProps = Omit<ComponentProps<"input">, "id"> &
  FieldChrome & { id?: string; fieldClassName?: string };

/** Label, hint, input and error wired together for assistive technology. Works with react-hook-form's `register`. */
export function TextField({
  label,
  hint,
  error,
  optional,
  id,
  className,
  fieldClassName,
  ...input
}: TextFieldProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <Chrome
      id={inputId}
      label={label}
      hint={hint}
      error={error}
      optional={optional}
      className={fieldClassName}
    >
      <input
        id={inputId}
        className={cx(s.control, className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, hint, error)}
        {...input}
      />
    </Chrome>
  );
}

type SelectFieldProps = Omit<ComponentProps<"select">, "id"> &
  FieldChrome & { id?: string; fieldClassName?: string };

/** A native select: accessible everywhere, and the best picker on a phone. */
export function SelectField({
  label,
  hint,
  error,
  optional,
  id,
  className,
  fieldClassName,
  children,
  ...select
}: SelectFieldProps) {
  const generated = useId();
  const selectId = id ?? generated;
  return (
    <Chrome
      id={selectId}
      label={label}
      hint={hint}
      error={error}
      optional={optional}
      className={fieldClassName}
    >
      <select
        id={selectId}
        className={cx(s.control, s.select, className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(selectId, hint, error)}
        {...select}
      >
        {children}
      </select>
    </Chrome>
  );
}

type TextareaFieldProps = Omit<ComponentProps<"textarea">, "id"> &
  FieldChrome & { id?: string; fieldClassName?: string };

export function TextareaField({
  label,
  hint,
  error,
  optional,
  id,
  className,
  fieldClassName,
  rows = 4,
  ...textarea
}: TextareaFieldProps) {
  const generated = useId();
  const areaId = id ?? generated;
  return (
    <Chrome
      id={areaId}
      label={label}
      hint={hint}
      error={error}
      optional={optional}
      className={fieldClassName}
    >
      <textarea
        id={areaId}
        rows={rows}
        className={cx(s.control, s.textarea, className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(areaId, hint, error)}
        {...textarea}
      />
    </Chrome>
  );
}
