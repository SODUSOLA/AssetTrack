import { ClipboardPlus, MessageSquarePlus, Pencil } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { isApiError } from "@/api/errors";
import { Button, ButtonLink } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { SelectField, TextField } from "@/components/ui/Fields";
import { DefinitionList, PageHeader } from "@/components/ui/Layout";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  AcknowledgeDialog,
  type AcknowledgeTarget,
} from "@/features/acknowledgements/AcknowledgeDialog";
import { useUser } from "@/features/auth/authContext";
import { RaiseComplaintDialog } from "@/features/complaints/RaiseComplaintDialog";
import { formatDate, formatDateOnly, plural } from "@/lib/format";
import { can } from "@/lib/permissions";
import s from "./DeviceDetailPage.module.css";
import { EditDeviceDialog } from "./DeviceFormDialog";
import { offeredEventTypes } from "./eventForms";
import { LogEventDialog } from "./LogEventDialog";
import { useDevice, useTimeline } from "./queries";
import { Timeline } from "./Timeline";

export function DeviceDetailPage() {
  const { deviceId = "" } = useParams();
  const user = useUser();
  const [params, setParams] = useSearchParams();
  const range = { from: params.get("from") || undefined, to: params.get("to") || undefined };
  const order = params.get("order") === "oldest" ? "oldest" : "newest";

  const device = useDevice(deviceId);
  const timeline = useTimeline(deviceId, range);

  const [logOpen, setLogOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [raiseOpen, setRaiseOpen] = useState(false);
  const [answering, setAnswering] = useState<AcknowledgeTarget | null>(null);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  if (device.isError) {
    if (isApiError(device.error) && device.error.status === 404) {
      return (
        <>
          <PageHeader
            title="Device not found"
            breadcrumbs={[{ label: "Devices", to: "/devices" }, { label: "Not found" }]}
          />
          <EmptyState
            title="There is no such device"
            description="It may have been typed wrongly, or it belongs to another unit."
            action={
              <ButtonLink to="/devices" variant="primary">
                Back to devices
              </ButtonLink>
            }
          />
        </>
      );
    }
    return (
      <ErrorState
        error={device.error}
        onRetry={() => void device.refetch()}
        title="This device could not be loaded"
      />
    );
  }

  const d = device.data;
  const canLog = !!d && can.logEvent(user) && offeredEventTypes(d.allowed_events).length > 0;
  const hasFilter = !!(range.from || range.to);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Devices", to: "/devices" }, { label: d?.asset_tag ?? "Device" }]}
        title={
          d ? <span className="mono">{d.asset_tag}</span> : <Skeleton width="12rem" height="2rem" />
        }
        subtitle={d ? [d.device_type, d.make, d.model].filter(Boolean).join(" · ") : undefined}
        actions={
          d && (
            <>
              {can.raiseComplaint(user) && d.unit && (
                <Button
                  icon={<MessageSquarePlus size={16} aria-hidden="true" />}
                  onClick={() => setRaiseOpen(true)}
                >
                  Raise a complaint
                </Button>
              )}
              {can.editDevice(user) && (
                <Button
                  icon={<Pencil size={16} aria-hidden="true" />}
                  onClick={() => setEditOpen(true)}
                >
                  Edit details
                </Button>
              )}
              {canLog && (
                <Button
                  variant="primary"
                  icon={<ClipboardPlus size={16} aria-hidden="true" />}
                  onClick={() => setLogOpen(true)}
                >
                  Log an event
                </Button>
              )}
            </>
          )
        }
      />

      <div className={s.stack}>
        <Panel title="Details">
          {!d ? (
            <Skeleton height="5rem" />
          ) : (
            <DefinitionList
              items={[
                { label: "Status", value: <StatusBadge status={d.status} /> },
                { label: "Unit", value: d.unit?.name ?? "Central stock (not with a unit)" },
                {
                  label: "Serial number",
                  value: d.serial_number ? <span className="mono">{d.serial_number}</span> : null,
                },
                { label: "Make and model", value: [d.make, d.model].filter(Boolean).join(" ") },
                { label: "Date acquired", value: formatDateOnly(d.acquired_on) },
                {
                  label: "Open complaints",
                  value:
                    d.open_complaint_count > 0 ? (
                      <Link to={`/complaints?device=${d.id}`}>
                        {plural(d.open_complaint_count, "complaint")}
                      </Link>
                    ) : (
                      "None"
                    ),
                },
                {
                  label: "Registered",
                  value: `${formatDate(d.created_at)} by ${d.created_by.full_name}`,
                },
              ]}
            />
          )}
        </Panel>

        <Panel
          title="Timeline"
          actions={
            <div className={s.filters}>
              <TextField
                label="From"
                type="date"
                value={range.from ?? ""}
                onChange={(e) => setParam("from", e.target.value)}
                fieldClassName={s.dateField}
              />
              <TextField
                label="To"
                type="date"
                value={range.to ?? ""}
                onChange={(e) => setParam("to", e.target.value)}
                fieldClassName={s.dateField}
              />
              <SelectField
                label="Order"
                value={order}
                onChange={(e) => setParam("order", e.target.value === "oldest" ? "oldest" : "")}
                fieldClassName={s.orderField}
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
              </SelectField>
              {hasFilter && (
                <Button
                  variant="quiet"
                  onClick={() => {
                    const next = new URLSearchParams(params);
                    next.delete("from");
                    next.delete("to");
                    setParams(next, { replace: true });
                  }}
                >
                  Clear dates
                </Button>
              )}
            </div>
          }
        >
          {timeline.isError ? (
            <ErrorState
              error={timeline.error}
              onRetry={() => void timeline.refetch()}
              title="The timeline could not be loaded"
            />
          ) : timeline.isPending ? (
            <Skeleton height="12rem" />
          ) : timeline.data.events.length === 0 ? (
            <EmptyState
              title={
                hasFilter ? "Nothing was recorded in these dates" : "Nothing has been recorded yet"
              }
              description={
                hasFilter ? "Widen the dates or clear them to see the whole history." : undefined
              }
            />
          ) : (
            <Timeline
              events={timeline.data.events}
              user={user}
              deviceTag={d?.asset_tag ?? ""}
              order={order}
              onAnswer={setAnswering}
            />
          )}
        </Panel>
      </div>

      {d && (
        <>
          <EditDeviceDialog device={d} open={editOpen} onOpenChange={setEditOpen} />
          {can.raiseComplaint(user) && d.unit && (
            <RaiseComplaintDialog
              open={raiseOpen}
              onOpenChange={setRaiseOpen}
              device={{ id: d.id, asset_tag: d.asset_tag, unit: d.unit }}
            />
          )}
          <LogEventDialog
            key={`${d.id}-${d.status}`}
            device={d}
            events={timeline.data?.events ?? []}
            open={logOpen}
            onOpenChange={setLogOpen}
          />
        </>
      )}
      <AcknowledgeDialog target={answering} onClose={() => setAnswering(null)} />
    </>
  );
}
