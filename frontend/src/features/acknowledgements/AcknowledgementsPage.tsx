import { Link, useSearchParams } from "react-router-dom";
import type { PendingAcknowledgement } from "@/api/types";
import { Stamp } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { SelectField } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Layout";
import { Pagination } from "@/components/ui/Pagination";
import { Panel } from "@/components/ui/Panel";
import { useUser } from "@/features/auth/authContext";
import { useUnits } from "@/features/units/queries";
import { formatDate, plural } from "@/lib/format";
import { EVENT_LABEL } from "@/lib/labels";
import { can } from "@/lib/permissions";
import { useState } from "react";
import { AcknowledgeDialog, type AcknowledgeTarget } from "./AcknowledgeDialog";
import { ACKS_PAGE_SIZE, usePendingAcknowledgements } from "./queries";
import s from "./AcknowledgementsPage.module.css";

export function AcknowledgementsPage() {
  const user = useUser();
  const isRep = user.role === "unit_rep";
  const [params, setParams] = useSearchParams();
  const [answering, setAnswering] = useState<AcknowledgeTarget | null>(null);

  const page = Math.max(1, Number(params.get("page")) || 1);
  const unit = params.get("unit") ?? "";
  const overdue = params.get("overdue");

  const units = useUnits(can.filterByUnit(user)); // reps see only their own unit
  const pending = usePendingAcknowledgements({
    page,
    ...(unit && can.filterByUnit(user) ? { unit_id: unit } : {}),
    ...(overdue === "yes" ? { overdue: true } : overdue === "no" ? { overdue: false } : {}),
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  const columns: Column<PendingAcknowledgement>[] = [
    {
      id: "what",
      header: "What happened",
      primary: true,
      cell: (row) => EVENT_LABEL[row.event_type],
    },
    {
      id: "device",
      header: "Device",
      cell: (row) => (
        <>
          <Link to={`/devices/${row.device.id}`} className="mono">
            {row.device.asset_tag}
          </Link>
          <span> · {row.device.device_type}</span>
        </>
      ),
    },
    { id: "unit", header: "Unit", cell: (row) => row.unit?.name ?? "-" },
    { id: "person", header: "With", cell: (row) => row.counterparty_name ?? "-" },
    { id: "since", header: "Recorded", cell: (row) => formatDate(row.occurred_at) },
    {
      id: "waiting",
      header: "Waiting",
      cell: (row) => (
        <Stamp
          state={row.overdue ? "overdue" : "pending"}
          detail={row.pending_days === 0 ? "today" : plural(row.pending_days, "day")}
        />
      ),
    },
    {
      id: "actions",
      header: "Your answer",
      cell: (row) =>
        can.acknowledge(user, row.unit?.id) ? (
          <span className={s.actions}>
            <Button
              size="sm"
              variant="primary"
              onClick={() =>
                setAnswering({
                  eventId: row.event_id,
                  what: EVENT_LABEL[row.event_type],
                  device: row.device.asset_tag,
                  mode: "confirm",
                })
              }
            >
              Confirm
            </Button>
            <Button
              size="sm"
              onClick={() =>
                setAnswering({
                  eventId: row.event_id,
                  what: EVENT_LABEL[row.event_type],
                  device: row.device.asset_tag,
                  mode: "dispute",
                })
              }
            >
              Dispute
            </Button>
          </span>
        ) : (
          <Link to={`/devices/${row.device.id}`}>View device</Link>
        ),
    },
  ];

  const filtered = !!(unit || overdue);

  return (
    <>
      <PageHeader
        title="Acknowledgements"
        subtitle={
          isRep
            ? "Handovers waiting for you to confirm or dispute."
            : "Handovers still waiting for a unit to answer. Nothing is ever confirmed for them."
        }
      />

      <Panel title="Waiting for an answer" flush>
        {!isRep && (
          <form
            role="search"
            aria-label="Filter acknowledgements"
            onSubmit={(e) => e.preventDefault()}
            className={s.filters}
          >
            <SelectField
              label="Unit"
              value={unit}
              onChange={(e) => setParam("unit", e.target.value)}
              fieldClassName=""
            >
              <option value="">All units</option>
              {units.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="How long"
              value={overdue ?? ""}
              onChange={(e) => setParam("overdue", e.target.value)}
            >
              <option value="">Everything pending</option>
              <option value="yes">Overdue only</option>
              <option value="no">Not yet overdue</option>
            </SelectField>
          </form>
        )}

        {pending.isError ? (
          <ErrorState
            error={pending.error}
            onRetry={() => void pending.refetch()}
            title="Acknowledgements could not be loaded"
          />
        ) : (
          <>
            <DataTable
              caption="Handovers waiting for an answer"
              columns={isRep ? columns.filter((c) => c.id !== "unit") : columns}
              rows={pending.data?.items ?? []}
              rowKey={(row) => row.event_id}
              loading={pending.isPending}
              empty={
                <EmptyState
                  title={
                    filtered
                      ? "Nothing matches these filters"
                      : isRep
                        ? "You are all caught up"
                        : "Nothing is waiting"
                  }
                  description={
                    filtered
                      ? "Clear the filters to see everything that is pending."
                      : isRep
                        ? "There are no handovers waiting for your answer."
                        : "Every handover has been answered."
                  }
                />
              }
            />
            {pending.data && (
              <Pagination
                page={page}
                pageSize={ACKS_PAGE_SIZE}
                total={pending.data.total}
                onPageChange={(next) => setParam("page", next > 1 ? String(next) : "")}
                noun="waiting"
              />
            )}
          </>
        )}
      </Panel>

      <AcknowledgeDialog target={answering} onClose={() => setAnswering(null)} />
    </>
  );
}
