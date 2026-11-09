import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, unwrap } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Feedback";
import { TextField } from "@/components/ui/Fields";
import { DefinitionList, PageHeader } from "@/components/ui/Layout";
import { Panel } from "@/components/ui/Panel";
import { useToast } from "@/components/ui/toastContext";
import { applyApiError } from "@/lib/forms";
import { ROLE_LABEL } from "@/lib/labels";
import { useUser } from "@/features/auth/authContext";
import s from "./AccountPage.module.css";

const schema = z
  .object({
    old_password: z.string().min(1, "Enter your current password"),
    new_password: z
      .string()
      .min(10, "Use at least 10 characters")
      .max(128, "Use no more than 128 characters"),
    confirm: z.string().min(1, "Type the new password again"),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ["confirm"],
    message: "The two passwords do not match",
  });
type Values = z.infer<typeof schema>;

export function AccountPage() {
  const user = useUser();
  const toast = useToast();
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { old_password: "", new_password: "", confirm: "" },
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = form;

  const change = useMutation({
    mutationFn: (values: Values) =>
      unwrap(
        api.POST("/api/v1/auth/change-password", {
          body: { old_password: values.old_password, new_password: values.new_password },
        }),
      ),
  });

  async function onSubmit(values: Values) {
    setProblem(null);
    try {
      await change.mutateAsync(values);
      reset();
      toast.show({
        title: "Password changed",
        description: "You were signed out of your other sessions.",
      });
    } catch (error) {
      setProblem(
        applyApiError(form, error, {
          INVALID_OLD_PASSWORD: "old_password",
          PASSWORD_UNCHANGED: "new_password",
        }),
      );
    }
  }

  return (
    <>
      <PageHeader title="Your account" breadcrumbs={[{ label: "Account" }]} />
      <div className={s.layout}>
        <Panel title="Profile">
          <DefinitionList
            items={[
              { label: "Name", value: user.full_name },
              { label: "Email", value: user.email },
              { label: "Role", value: ROLE_LABEL[user.role] },
            ]}
          />
        </Panel>

        <Panel title="Change password">
          <form className={s.form} onSubmit={handleSubmit(onSubmit)} noValidate>
            {problem && <Alert tone="error">{problem}</Alert>}
            <TextField
              label="Current password"
              type="password"
              autoComplete="current-password"
              error={errors.old_password?.message}
              {...register("old_password")}
            />
            <TextField
              label="New password"
              type="password"
              autoComplete="new-password"
              hint="At least 10 characters."
              error={errors.new_password?.message}
              {...register("new_password")}
            />
            <TextField
              label="Repeat the new password"
              type="password"
              autoComplete="new-password"
              error={errors.confirm?.message}
              {...register("confirm")}
            />
            <div>
              <Button type="submit" variant="primary" loading={change.isPending}>
                Change password
              </Button>
            </div>
          </form>
        </Panel>
      </div>
    </>
  );
}
