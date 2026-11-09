import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import type { User, UserRole } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { SelectField, TextField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { useUnits } from "@/features/units/queries";
import { useCreateUser, useUpdateUser } from "@/features/users/queries";
import { applyApiError } from "@/lib/forms";
import { ROLE_LABEL } from "@/lib/labels";
import { generatePassword } from "@/lib/password";
import s from "./Admin.module.css";

const ROLES = Object.keys(ROLE_LABEL) as UserRole[];

const schema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(1, "Enter the person's full name")
      .max(200, "Keep this under 200 characters"),
    email: z.string().trim(),
    role: z.enum(["admin", "engineer", "unit_rep", "auditor"]),
    unit_id: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.role === "unit_rep" && !v.unit_id) {
      ctx.addIssue({
        code: "custom",
        path: ["unit_id"],
        message: "Choose the unit this person represents",
      });
    }
  });
type Values = z.infer<typeof schema>;

export type Created = { user: User; password: string };

/**
 * Create an account (the starting password is generated and handed back once) or edit one. There
 * is no email field when editing: an email is the person's identity in the record.
 */
export function UserFormDialog({
  user,
  isSelf = false,
  open,
  onOpenChange,
  onCreated,
}: {
  /** Omit to create a new user. */
  user?: User;
  /** An administrator cannot change their own role: that could lock everyone out. */
  isSelf?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (created: Created) => void;
}) {
  const toast = useToast();
  const create = useCreateUser();
  const update = useUpdateUser();
  const units = useUnits(open);
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    values: {
      full_name: user?.full_name ?? "",
      email: user?.email ?? "",
      role: user?.role ?? "engineer",
      unit_id: user?.unit_id ?? "",
    },
  });
  const {
    register,
    control,
    setError,
    formState: { errors },
  } = form;
  const role = useWatch({ control, name: "role" });
  const pending = create.isPending || update.isPending;

  function close(next: boolean) {
    if (!next) {
      setProblem(null);
      form.reset();
    }
    onOpenChange(next);
  }

  async function onSubmit(values: Values) {
    setProblem(null);
    const unit_id = values.role === "unit_rep" ? values.unit_id : null;
    try {
      if (user) {
        await update.mutateAsync({
          id: user.id,
          body: {
            full_name: values.full_name,
            ...(isSelf ? {} : { role: values.role, unit_id }),
          },
        });
        toast.show({ title: "Saved", description: values.full_name });
        close(false);
      } else {
        if (!values.email) {
          setError("email", { message: "Enter their email address" });
          return;
        }
        const password = generatePassword();
        const created = await create.mutateAsync({
          full_name: values.full_name,
          email: values.email,
          role: values.role,
          password,
          ...(unit_id ? { unit_id } : {}),
        });
        close(false);
        onCreated?.({ user: created, password });
      }
    } catch (error) {
      setProblem(applyApiError(form, error, { EMAIL_TAKEN: "email" }));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title={user ? "Edit person" : "Add a person"}
      description={
        user
          ? undefined
          : "A starting password is made for you to pass on. The person changes it after signing in."
      }
      footer={
        <>
          <Button onClick={() => close(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="user-form" loading={pending}>
            {user ? "Save" : "Add person"}
          </Button>
        </>
      }
    >
      <form id="user-form" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        {problem && <Alert tone="error">{problem}</Alert>}
        <div className={s.fields}>
          <TextField
            label="Full name"
            autoComplete="off"
            autoFocus
            error={errors.full_name?.message}
            {...register("full_name")}
          />
          {!user && (
            <TextField
              label="Email address"
              type="email"
              autoComplete="off"
              hint="They sign in with this."
              error={errors.email?.message}
              {...register("email")}
            />
          )}
          <SelectField
            label="Role"
            disabled={isSelf}
            hint={isSelf ? "You cannot change your own role." : undefined}
            error={errors.role?.message}
            {...register("role")}
          >
            {ROLES.map((value) => (
              <option key={value} value={value}>
                {ROLE_LABEL[value]}
              </option>
            ))}
          </SelectField>
          {role === "unit_rep" && (
            <SelectField
              label="Unit they represent"
              disabled={isSelf || units.isPending}
              error={errors.unit_id?.message}
              {...register("unit_id")}
            >
              <option value="">{units.isPending ? "Loading units…" : "Choose a unit"}</option>
              {units.data
                ?.filter((u) => u.is_active || u.id === user?.unit_id)
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
            </SelectField>
          )}
        </div>
      </form>
    </Dialog>
  );
}
