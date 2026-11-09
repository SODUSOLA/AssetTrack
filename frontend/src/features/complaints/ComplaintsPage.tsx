import { Plus } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ComplaintOut, ComplaintStatus, PriorityLevel } from "@/api/types";
import { ComplaintStatusBadge, PriorityBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { SelectField, TextField } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Layout";
import { Pagination } from "@/components/ui/Pagination";
import { Panel } from "@/components/ui/Panel";
import { useUser } from "@/features/auth/authContext";
import { useUnits } from "@/features/units/queries";
import { formatDate, formatRelative } from "@/lib/format";
import { COMPLAINT_STATUS_LABEL, PRIORITY_LABEL } from "@/lib/labels";
import { can } from "@/lib/permissions";
import s from "./ComplaintsPage.module.css";
import { COMPLAINTS_PAGE_SIZE, useComplaints } from "./queries";
import { RaiseComplaintDialog } from "./RaiseComplaintDialog";

const STATUSES = Object.keys(COMPLAINT_STATUS_LABEL) as ComplaintStatus[];
const PRIORITIES = Object.keys(PRIORITY_LABEL) as PriorityLevel[];

function makeColumns(showUnit: boolean): Column<ComplaintOut>[] {
  return [
    {
      id: "ticket",
      header: "Ticket",
      primary: true,
      cell: (c) => (
        <>
          <Link to={`/complaints/${c.id}`} className="mono">
            {c.ticket_no}
          </Link>
          <span className={s.sub}>{c.title}</span>
        </>
      ),
    },
    ...(showUnit ? [{ id: "unit", header: "Unit", cell: (c: ComplaintOut) => c.unit.name }] : []),
    {
      id: "device",
      header: "Device",
      cell: (c) =>
        c.device ? (
          <Link to={`/devices/${c.device.id}`} className="mono">
            {c.device.asset_tag}
          </Link>
        ) : (
          "-"
        ),
    },
    { id: "priority", header: "Priority", cell: (c) => <PriorityBadge priority={c.priority} /> },
    { id: "status", header: "Status", cell: (c) => <ComplaintStatusBadge status={c.status} /> },
    {
      id: "assignee",
      header: "Assigned to",
      cell: (c) => c.assigned_to?.full_name ?? "Nobody yet",
    },
    {
      id: "raised",
      header: "Raised",
      cell: (c) => <span title={formatDate(c.created_at)}>{formatRelative(c.created_at)}</span>,
    },
  ];
}

export function ComplaintsPage() {
  const user = useUser();
  const isStaff = can.filterByUnit(user) && user.role !== "auditor";
  const [params, setParams] = useSearchParams();
  const [raising, setRaising] = useState(false);

  const page = Math.max(1, Number(params.get("page")) || 1);
  const status = (params.get("status") as ComplaintStatus | null) ?? undefined;
  const priority = (params.get("priority") as PriorityLevel | null) ?? undefined;
  const unit = params.get("unit") ?? "";
  const mine = params.get("mine") === "yes";
  const deviceId = params.get("device") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";

  const units = useUnits(can.filterByUnit(user));
  const complaints = useComplaints({
    page,
    ...(status ? { status } : {}),
    ...(priority ? { priority } : {}),
    ...(unit && can.filterByUnit(user) ? { unit_id: unit } : {}),
    ...(mine ? { assigned_to: user.id } : {}),
    ...(deviceId ? { device_id: deviceId } : {}),
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  const filtered = !!(status || priority || unit || mine || deviceId || from || to);
  const total = complaints.data?.total;

  return (
    <>
      <PageHeader
        title="Complaints"
        subtitle={
          total !== undefined
            ? `${total} ${filtered ? "matching complaints" : "complaints"}`
            : undefined
        }
        actions={
          can.raiseComplaint(user) && (
            <Button
              variant="primary"
              icon={<Plus size={16} aria-hidden="true" />}
              onClick={() => setRaising(true)}
            >
              Raise a complaint
            </Button>
          )
        }
      />

      <Panel title="All complaints" flush>
        <form
          className={s.filters}
          role="search"
          aria-label="Filter complaints"
          onSubmit={(e) => e.preventDefault()}
        >
          <SelectField
            label="Status"
            value={status ?? ""}
            onChange={(e) => setParam("status", e.target.value)}
            fieldClassName={s.select}
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {COMPLAINT_STATUS_LABEL[value]}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Priority"
            value={priority ?? ""}
            onChange={(e) => setParam("priority", e.target.value)}
            fieldClassName={s.select}
          >
            <option value="">Any priority</option>
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {PRIORITY_LABEL[value]}
              </option>
            ))}
          </SelectField>
          {can.filterByUnit(user) && (
            <SelectField
              label="Unit"
              value={unit}
              onChange={(e) => setParam("unit", e.target.value)}
              fieldClassName={s.select}
            >
              <option value="">All units</option>
              {units.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </SelectField>
          )}
          {isStaff && (
            <SelectField
              label="Assigned to"
              value={mine ? "yes" : ""}
              onChange={(e) => setParam("mine", e.target.value)}
              fieldClassName={s.select}
            >
              <option value="">Anyone</option>
              <option value="yes">Me</option>
            </SelectField>
          )}
          <TextField
            label="Raised from"
            type="date"
            value={from}
            onChange={(e) => setParam("from", e.target.value)}
            fieldClassName={s.date}
          />
          <TextField
            label="Raised to"
            type="date"
            value={to}
            onChange={(e) => setParam("to", e.target.value)}
            fieldClassName={s.date}
          />
          {filtered && (
            <Button variant="quiet" onClick={() => setParams({}, { replace: true })}>
              Clear filters
            </Button>
          )}
        </form>

        {complaints.isError ? (
          <ErrorState
            error={complaints.error}
            onRetry={() => void complaints.refetch()}
            title="Complaints could not be loaded"
          />
        ) : (
          <>
            <DataTable
              caption="Complaints"
              cardsBelow={960}
              columns={makeColumns(can.filterByUnit(user))}
              rows={complaints.data?.items ?? []}
              rowKey={(c) => c.id}
              loading={complaints.isPending}
              empty={
                filtered ? (
                  <EmptyState
                    title="No complaints match"
                    description="Try different filters, or clear them."
                    action={
                      <Button onClick={() => setParams({}, { replace: true })}>
                        Clear filters
                      </Button>
                    }
                  />
                ) : (
                  <EmptyState
                    title="No complaints yet"
                    description={
                      can.raiseComplaint(user)
                        ? "When something is wrong with a device, raise a complaint so it is on the record."
                        : "Complaints appear here once a unit raises them."
                    }
                    action={
                      can.raiseComplaint(user) ? (
                        <Button variant="primary" onClick={() => setRaising(true)}>
                          Raise a complaint
                        </Button>
                      ) : undefined
                    }
                  />
                )
              }
            />
            {complaints.data && (
              <Pagination
                page={complaints.data.page}
                pageSize={COMPLAINTS_PAGE_SIZE}
                total={complaints.data.total}
                onPageChange={(next) => setParam("page", String(next))}
                noun="complaints"
              />
            )}
          </>
        )}
      </Panel>

      <RaiseComplaintDialog open={raising} onOpenChange={setRaising} />
    </>
  );
}
