import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { Unit } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { TextField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { useCreateUnit, useUpdateUnit } from "@/features/units/queries";
import { applyApiError } from "@/lib/forms";
import s from "./Admin.module.css";

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter the unit's name")
    .max(100, "Keep this under 100 characters"),
  code: z.string().trim().min(1, "Enter a short code").max(20, "Keep the code under 20 characters"),
});
type Values = z.infer<typeof schema>;

/** Create a unit, or rename one. A unit is never deleted: records point at it. */
export function UnitFormDialog({
  unit,
  open,
  onOpenChange,
}: {
  /** Omit to create a new unit. */
  unit?: Unit;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const toast = useToast();
  const create = useCreateUnit();
  const update = useUpdateUnit();
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    values: { name: unit?.name ?? "", code: unit?.code ?? "" },
  });
  const pending = create.isPending || update.isPending;
  const {
    register,
    formState: { errors },
  } = form;

  function close(next: boolean) {
    if (!next) {
      setProblem(null);
      form.reset();
    }
    onOpenChange(next);
  }

  async function onSubmit(values: Values) {
    setProblem(null);
    try {
      if (unit) await update.mutateAsync({ id: unit.id, body: values });
      else await create.mutateAsync(values);
      toast.show({ title: unit ? "Unit saved" : "Unit created", description: values.name });
      close(false);
    } catch (error) {
      setProblem(applyApiError(form, error));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title={unit ? "Edit unit" : "Add a unit"}
      description={
        unit ? "Changing the name or code does not change any record already made." : undefined
      }
      footer={
        <>
          <Button onClick={() => close(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="unit-form" loading={pending}>
            {unit ? "Save" : "Add unit"}
          </Button>
        </>
      }
    >
      <form id="unit-form" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        {problem && <Alert tone="error">{problem}</Alert>}
        <div className={s.fields}>
          <TextField
            label="Name"
            autoComplete="off"
            autoFocus
            error={errors.name?.message}
            {...register("name")}
          />
          <TextField
            label="Code"
            autoComplete="off"
            hint="A short code, for example REG."
            error={errors.code?.message}
            {...register("code")}
          />
        </div>
      </form>
    </Dialog>
  );
}
