import type { FieldValues, Path, UseFormReturn } from "react-hook-form";
import { isApiError } from "@/api/errors";
import { describeError } from "@/lib/messages";

/**
 * Show a server error on the form: validation messages go on their own fields, and a known code
 * can be pinned to a field (`{ SERIAL_EXISTS: "serial_number" }`). Anything left over is returned
 * as one sentence for the form-level alert, so no error is ever swallowed.
 */
export function applyApiError<T extends FieldValues>(
  form: UseFormReturn<T>,
  error: unknown,
  codeToField: Record<string, Path<T>> = {},
): string | null {
  if (!isApiError(error)) return describeError(error);

  const known = new Set<string>(Object.keys(form.getValues()));
  let placed = 0;
  for (const [field, message] of Object.entries(error.fieldErrors)) {
    if (known.has(field)) {
      form.setError(field as Path<T>, { type: "server", message });
      placed += 1;
    }
  }
  const pinned = codeToField[error.code];
  if (pinned) {
    form.setError(pinned, { type: "server", message: describeError(error) });
    return null;
  }
  return placed > 0 ? null : describeError(error);
}
