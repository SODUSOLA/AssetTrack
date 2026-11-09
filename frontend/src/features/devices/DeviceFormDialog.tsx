import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import type { DeviceDetail } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { TextField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { applyApiError } from "@/lib/forms";
import { DEVICE_TYPE_SUGGESTIONS } from "@/lib/labels";
import s from "./DeviceFormDialog.module.css";
import { useRegisterDevice, useUpdateDevice } from "./queries";

const schema = z.object({
  device_type: z
    .string()
    .trim()
    .min(1, "Enter the kind of device")
    .max(50, "Keep this under 50 characters"),
  serial_number: z.string().trim().max(100, "Keep this under 100 characters"),
  make: z.string().trim().max(100, "Keep this under 100 characters"),
  model: z.string().trim().max(100, "Keep this under 100 characters"),
  acquired_on: z.string(),
});
type Values = z.infer<typeof schema>;

const CODE_TO_FIELD = { SERIAL_EXISTS: "serial_number" } as const;

function valuesFor(device?: DeviceDetail): Values {
  return {
    device_type: device?.device_type ?? "",
    serial_number: device?.serial_number ?? "",
    make: device?.make ?? "",
    model: device?.model ?? "",
    acquired_on: device?.acquired_on ?? "",
  };
}

function Fields({ form }: { form: ReturnType<typeof useForm<Values>> }) {
  const {
    register,
    formState: { errors },
  } = form;
  return (
    <div className={s.fields}>
      <TextField
        label="Type of device"
        list="device-type-suggestions"
        autoComplete="off"
        autoFocus
        error={errors.device_type?.message}
        {...register("device_type")}
      />
      <datalist id="device-type-suggestions">
        {DEVICE_TYPE_SUGGESTIONS.map((type) => (
          <option key={type} value={type} />
        ))}
      </datalist>
      <TextField
        label="Serial number"
        optional
        autoComplete="off"
        hint="Must be unique. Letter case does not matter."
        error={errors.serial_number?.message}
        {...register("serial_number")}
      />
      <div className={s.pair}>
        <TextField
          label="Make"
          optional
          autoComplete="off"
          error={errors.make?.message}
          {...register("make")}
        />
        <TextField
          label="Model"
          optional
          autoComplete="off"
          error={errors.model?.message}
          {...register("model")}
        />
      </div>
      <TextField
        label="Date acquired"
        optional
        type="date"
        error={errors.acquired_on?.message}
        {...register("acquired_on")}
      />
    </div>
  );
}

/** Register a new device. It starts in central stock; handing it to a unit is a separate, recorded step. */
export function RegisterDeviceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const register = useRegisterDevice();
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: valuesFor() });

  function close(next: boolean) {
    if (!next) {
      setProblem(null);
      form.reset(valuesFor());
    }
    onOpenChange(next);
  }

  async function onSubmit(values: Values) {
    setProblem(null);
    try {
      const device = await register.mutateAsync({
        device_type: values.device_type,
        ...(values.serial_number ? { serial_number: values.serial_number } : {}),
        ...(values.make ? { make: values.make } : {}),
        ...(values.model ? { model: values.model } : {}),
        ...(values.acquired_on ? { acquired_on: values.acquired_on } : {}),
      });
      toast.show({ title: "Device registered", description: device.asset_tag });
      close(false);
      void navigate(`/devices/${device.id}`);
    } catch (error) {
      setProblem(applyApiError(form, error, CODE_TO_FIELD));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Register a device"
      description="It gets an asset tag automatically and starts in central stock."
      footer={
        <>
          <Button onClick={() => close(false)} disabled={register.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="register-device"
            loading={register.isPending}
          >
            Register device
          </Button>
        </>
      }
    >
      <form id="register-device" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        {problem && <Alert tone="error">{problem}</Alert>}
        <Fields form={form} />
      </form>
    </Dialog>
  );
}

/** Correct a device's details. Each real change is written to the device's record as a note. */
export function EditDeviceDialog({
  device,
  open,
  onOpenChange,
}: {
  device: DeviceDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const toast = useToast();
  const update = useUpdateDevice(device.id);
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: valuesFor(device) });

  function close(next: boolean) {
    if (!next) {
      setProblem(null);
      form.reset(valuesFor(device));
    }
    onOpenChange(next);
  }

  async function onSubmit(values: Values) {
    setProblem(null);
    const original = valuesFor(device);
    const body: Record<string, string | null> = {};
    for (const key of Object.keys(values) as Array<keyof Values>) {
      if (values[key] === original[key]) continue;
      // Clearing an optional field is sent as null; the device type can never be empty.
      body[key] = values[key] === "" ? null : values[key];
    }
    if (Object.keys(body).length === 0) {
      toast.show({ title: "Nothing was changed", tone: "info" });
      close(false);
      return;
    }
    try {
      await update.mutateAsync(body);
      toast.show({ title: "Details updated", description: "The change was added to the record." });
      close(false);
    } catch (error) {
      setProblem(applyApiError(form, error, CODE_TO_FIELD));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Edit device details"
      description="Status and unit change only through recorded steps, so they are not editable here."
      footer={
        <>
          <Button onClick={() => close(false)} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="edit-device" loading={update.isPending}>
            Save changes
          </Button>
        </>
      }
    >
      <form id="edit-device" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        {problem && <Alert tone="error">{problem}</Alert>}
        <Fields form={form} />
      </form>
    </Dialog>
  );
}
