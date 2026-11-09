import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import type { ComplaintCategory, PriorityLevel, UnitRef } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { SelectField, TextareaField, TextField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { useUser } from "@/features/auth/authContext";
import { useDevices } from "@/features/devices/queries";
import { useUnits } from "@/features/units/queries";
import { applyApiError } from "@/lib/forms";
import { CATEGORY_LABEL, PRIORITY_LABEL } from "@/lib/labels";
import s from "./ComplaintForms.module.css";
import { useRaiseComplaint } from "./queries";

export type RaiseFor = { id: string; asset_tag: string; unit: UnitRef | null };

const CATEGORIES = Object.keys(CATEGORY_LABEL) as ComplaintCategory[];
const PRIORITIES = Object.keys(PRIORITY_LABEL) as PriorityLevel[];

function makeSchema(needsUnit: boolean) {
  return z.object({
    unit_id: needsUnit ? z.string().min(1, "Choose the unit this is for") : z.string(),
    device_id: z.string(),
    category: z.enum(["hardware", "software", "network", "other"]),
    priority: z.enum(["low", "medium", "high", "critical"]),
    title: z
      .string()
      .trim()
      .min(1, "Give the problem a short title")
      .max(200, "Keep the title under 200 characters"),
    description: z
      .string()
      .trim()
      .min(1, "Describe what is wrong")
      .max(5000, "Keep this under 5000 characters"),
  });
}
type Values = z.infer<ReturnType<typeof makeSchema>>;

/**
 * Raise a complaint. A unit's representative raises it for their own unit (the server always
 * uses their unit); staff raise it on a unit's behalf and so must name the unit. A device is
 * optional: engineering links the ticket when the device is taken in.
 */
export function RaiseComplaintDialog({
  open,
  onOpenChange,
  device,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Raising from a device's page: the device and its unit are already known. */
  device?: RaiseFor;
}) {
  const user = useUser();
  const navigate = useNavigate();
  const toast = useToast();
  const raise = useRaiseComplaint();
  const [problem, setProblem] = useState<string | null>(null);

  const isRep = user.role === "unit_rep";
  const needsUnit = !isRep && !device;
  const schema = useMemo(() => makeSchema(needsUnit), [needsUnit]);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      unit_id: device?.unit?.id ?? "",
      device_id: device?.id ?? "",
      category: "hardware",
      priority: "medium",
      title: "",
      description: "",
    },
  });
  const {
    register,
    control,
    setValue,
    formState: { errors },
  } = form;

  const unitId = useWatch({ control, name: "unit_id" });
  const units = useUnits(needsUnit && open);
  // A rep's devices are scoped by the server; for staff, the devices of the chosen unit.
  const devices = useDevices(
    { page: 1, page_size: 100, ...(isRep ? {} : { unit_id: unitId }) },
    open && !device && (isRep || !!unitId),
  );

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
      const complaint = await raise.mutateAsync({
        title: values.title,
        description: values.description,
        category: values.category,
        priority: values.priority,
        ...(values.device_id ? { device_id: values.device_id } : {}),
        ...(!isRep && values.unit_id ? { unit_id: values.unit_id } : {}),
      });
      toast.show({ title: "Complaint raised", description: complaint.ticket_no });
      close(false);
      void navigate(`/complaints/${complaint.id}`);
    } catch (error) {
      setProblem(applyApiError(form, error));
    }
  }

  const deviceChoices = (devices.data?.items ?? []).filter((d) => d.status !== "decommissioned");

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Raise a complaint"
      description={
        device
          ? `About ${device.asset_tag}. It goes on the record as soon as you send it.`
          : "It goes on the record as soon as you send it."
      }
      size="lg"
      footer={
        <>
          <Button onClick={() => close(false)} disabled={raise.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="raise-complaint" loading={raise.isPending}>
            Raise complaint
          </Button>
        </>
      }
    >
      <form id="raise-complaint" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        {problem && <Alert tone="error">{problem}</Alert>}
        <div className={s.fields}>
          {needsUnit && (
            <SelectField
              label="Unit this is for"
              error={errors.unit_id?.message}
              disabled={units.isPending}
              {...register("unit_id", { onChange: () => setValue("device_id", "") })}
            >
              <option value="">{units.isPending ? "Loading units…" : "Choose a unit"}</option>
              {units.data
                ?.filter((u) => u.is_active)
                .map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
            </SelectField>
          )}
          <TextField
            label="Title"
            autoComplete="off"
            autoFocus={!needsUnit}
            hint="A few words: what is wrong, and with what."
            error={errors.title?.message}
            {...register("title")}
          />
          <TextareaField
            label="What is wrong"
            error={errors.description?.message}
            {...register("description")}
          />
          <div className={s.pair}>
            <SelectField label="Kind of problem" {...register("category")}>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {CATEGORY_LABEL[value]}
                </option>
              ))}
            </SelectField>
            <SelectField label="How urgent" {...register("priority")}>
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {PRIORITY_LABEL[value]}
                </option>
              ))}
            </SelectField>
          </div>
          {!device && (
            <SelectField
              label="Device"
              optional
              hint="Leave empty if you are not sure; engineering links it when the device is brought in."
              disabled={!isRep && !unitId}
              {...register("device_id")}
            >
              <option value="">
                {!isRep && !unitId
                  ? "Choose a unit first"
                  : devices.isPending
                    ? "Loading devices…"
                    : "Not sure yet"}
              </option>
              {deviceChoices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.asset_tag} · {d.device_type}
                </option>
              ))}
            </SelectField>
          )}
        </div>
      </form>
    </Dialog>
  );
}
