import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import type { DeviceDetail, EventBody, EventType, TimelineEvent } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { SelectField, TextareaField, TextField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { useUnits } from "@/features/units/queries";
import { formatDateTime } from "@/lib/format";
import { applyApiError } from "@/lib/forms";
import { EVENT_LABEL } from "@/lib/labels";
import s from "./DeviceFormDialog.module.css";
import {
  buildEventBody,
  buildEventSchema,
  EVENT_FORMS,
  offeredEventTypes,
  type FieldSpec,
} from "./eventForms";
import { useIntakeTickets, useLogEvent } from "./queries";

function EventForm({
  type,
  device,
  events,
  onDone,
  formId,
  onPendingChange,
}: {
  type: EventType;
  device: DeviceDetail;
  events: TimelineEvent[];
  onDone: () => void;
  formId: string;
  onPendingChange: (pending: boolean) => void;
}) {
  const spec = EVENT_FORMS[type]!;
  const toast = useToast();
  const logEvent = useLogEvent(device.id);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<Record<string, string> | null>(null);

  const needs = (kind: FieldSpec["kind"]) => spec.fields.some((f) => f.kind === kind);
  const units = useUnits();
  const tickets = useIntakeTickets(device.unit?.id, device.id, needs("ticket"));

  const schema = useMemo(() => buildEventSchema(spec.fields), [spec]);
  const form = useForm<Record<string, string>>({
    resolver: zodResolver(schema),
    defaultValues: Object.fromEntries(spec.fields.map((f) => [f.name, ""])),
  });
  const { register, formState } = form;

  async function send(values: Record<string, string>) {
    setProblem(null);
    onPendingChange(true);
    try {
      await logEvent.mutateAsync(buildEventBody(type, values) as EventBody);
      toast.show({ title: `${EVENT_LABEL[type]} recorded`, description: device.asset_tag });
      onDone();
    } catch (error) {
      setProblem(applyApiError(form, error));
    } finally {
      onPendingChange(false);
    }
  }

  function field(f: FieldSpec) {
    const error = formState.errors[f.name]?.message as string | undefined;
    const common = {
      label: f.label,
      hint: f.hint,
      error,
      optional: !f.required,
      ...register(f.name),
    };
    switch (f.kind) {
      case "textarea":
        return <TextareaField key={f.name} {...common} />;
      case "unit":
        return (
          <SelectField key={f.name} {...common} disabled={units.isPending}>
            <option value="">{units.isPending ? "Loading units…" : "Choose a unit"}</option>
            {units.data
              ?.filter((u) => u.is_active)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
          </SelectField>
        );
      case "ticket":
        return (
          <SelectField
            key={f.name}
            {...common}
            disabled={tickets.isPending}
            hint={
              tickets.data?.length === 0
                ? "This unit has no open complaint for this device. A unit representative can raise one."
                : f.hint
            }
          >
            <option value="">
              {tickets.isPending ? "Loading complaints…" : "Choose a complaint"}
            </option>
            {tickets.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.ticket_no} · {t.title}
              </option>
            ))}
          </SelectField>
        );
      case "event":
        return (
          <SelectField key={f.name} {...common}>
            <option value="">Not correcting an earlier entry</option>
            {[...events].reverse().map((e) => (
              <option key={e.id} value={e.id}>
                #{e.id} · {EVENT_LABEL[e.event_type]} · {formatDateTime(e.occurred_at)}
              </option>
            ))}
          </SelectField>
        );
      default:
        return <TextField key={f.name} {...common} autoComplete="off" />;
    }
  }

  return (
    <>
      <form
        id={formId}
        noValidate
        onSubmit={form.handleSubmit((values) =>
          spec.destructive ? setConfirming(values) : send(values),
        )}
      >
        {problem && <Alert tone="error">{problem}</Alert>}
        <div className={s.fields}>{spec.fields.map(field)}</div>
      </form>
      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => !open && setConfirming(null)}
        title={`${EVENT_LABEL[type]}: are you sure?`}
        description={`${device.asset_tag} will be retired and can take no more repair steps. This cannot be undone.`}
        confirmLabel="Yes, decommission"
        tone="danger"
        loading={logEvent.isPending}
        onConfirm={() => {
          const values = confirming;
          setConfirming(null);
          if (values) void send(values);
        }}
      />
    </>
  );
}

/**
 * Record the next step in a device's life. The step choices come from the server (`allowed_events`),
 * so the form can never offer something the state machine will refuse.
 */
export function LogEventDialog({
  device,
  events,
  open,
  onOpenChange,
}: {
  device: DeviceDetail;
  events: TimelineEvent[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const types = offeredEventTypes(device.allowed_events);
  const [chosen, setChosen] = useState<EventType | null>(null);
  const [pending, setPending] = useState(false);
  const type = chosen && types.includes(chosen) ? chosen : types[0];

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Log an event"
      description={<span className="mono">{device.asset_tag}</span>}
      size="lg"
      footer={
        <>
          <Button onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="log-event"
            loading={pending}
            disabled={!type}
          >
            Record event
          </Button>
        </>
      }
    >
      {!type ? (
        <Alert tone="info">No further steps can be recorded for this device.</Alert>
      ) : (
        <div className={s.fields}>
          <SelectField
            label="What happened"
            value={type}
            onChange={(event) => setChosen(event.target.value as EventType)}
            hint={EVENT_FORMS[type]?.help}
          >
            {types.map((t) => (
              <option key={t} value={t}>
                {EVENT_LABEL[t]}
              </option>
            ))}
          </SelectField>
          <EventForm
            key={type}
            type={type}
            device={device}
            events={events}
            formId="log-event"
            onPendingChange={setPending}
            onDone={() => onOpenChange(false)}
          />
        </div>
      )}
    </Dialog>
  );
}
