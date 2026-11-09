import { Plus } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Device, DeviceStatus } from "@/api/types";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { SelectField, TextField } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Layout";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Pagination } from "@/components/ui/Pagination";
import { Panel } from "@/components/ui/Panel";
import { useUser } from "@/features/auth/authContext";
import { useUnits } from "@/features/units/queries";
import { DEVICE_STATUS_LABEL, DEVICE_TYPE_SUGGESTIONS } from "@/lib/labels";
import { can } from "@/lib/permissions";
import s from "./DevicesPage.module.css";
import { RegisterDeviceDialog } from "./DeviceFormDialog";
import { DEVICES_PAGE_SIZE, useDevices } from "./queries";

const STATUSES = Object.keys(DEVICE_STATUS_LABEL) as DeviceStatus[];

const columns: Column<Device>[] = [
  {
    id: "tag",
    header: "Asset tag",
    primary: true,
    cell: (d) => (
      <Link to={`/devices/${d.id}`} className="mono">
        {d.asset_tag}
      </Link>
    ),
  },
  { id: "type", header: "Type", cell: (d) => d.device_type },
  {
    id: "model",
    header: "Make and model",
    cell: (d) => [d.make, d.model].filter(Boolean).join(" ") || "-",
  },
  {
    id: "serial",
    header: "Serial number",
    cell: (d) => (d.serial_number ? <span className="mono">{d.serial_number}</span> : "-"),
  },
  { id: "unit", header: "Unit", cell: (d) => d.unit?.name ?? "Central stock" },
  { id: "status", header: "Status", cell: (d) => <StatusBadge status={d.status} /> },
];

export function DevicesPage() {
  const user = useUser();
  const [params, setParams] = useSearchParams();
  const [registering, setRegistering] = useState(false);
  const [search, setSearch] = useState(params.get("q") ?? "");
  const timer = useRef<number | undefined>(undefined);

  const page = Math.max(1, Number(params.get("page")) || 1);
  const q = params.get("q") ?? "";
  const status = (params.get("status") as DeviceStatus | null) ?? undefined;
  const type = params.get("type") ?? "";
  const unit = params.get("unit") ?? "";

  const units = useUnits(can.filterByUnit(user)); // reps see only their own unit
  const devices = useDevices({
    page,
    ...(q ? { q } : {}),
    ...(status ? { status } : {}),
    ...(type ? { device_type: type } : {}),
    ...(unit && can.filterByUnit(user) ? { unit_id: unit } : {}),
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page"); // a new filter starts from the first page
    setParams(next, { replace: true });
  }

  function onSearch(value: string) {
    setSearch(value);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setParam("q", value.trim()), 300);
  }

  const filtered = !!(q || status || type || unit);
  function clearFilters() {
    setSearch("");
    setParams({}, { replace: true });
  }

  const total = devices.data?.total;
  const noun = filtered ? "matching devices" : "devices";

  return (
    <>
      <PageHeader
        title="Devices"
        subtitle={total !== undefined ? `${total} ${noun}` : undefined}
        actions={
          can.registerDevice(user) && (
            <Button
              variant="primary"
              icon={<Plus size={16} aria-hidden="true" />}
              onClick={() => setRegistering(true)}
            >
              Register a device
            </Button>
          )
        }
      />

      <Panel title="All devices" flush>
        <form
          className={s.filters}
          role="search"
          aria-label="Filter devices"
          onSubmit={(e) => e.preventDefault()}
        >
          <TextField
            label="Search"
            type="search"
            placeholder="Asset tag or serial number"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            fieldClassName={s.search}
            autoComplete="off"
          />
          <SelectField
            label="Status"
            value={status ?? ""}
            onChange={(e) => setParam("status", e.target.value)}
            fieldClassName={s.select}
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {DEVICE_STATUS_LABEL[value]}
              </option>
            ))}
          </SelectField>
          <TextField
            label="Type"
            list="devices-type-suggestions"
            placeholder="e.g. laptop"
            value={type}
            onChange={(e) => setParam("type", e.target.value)}
            fieldClassName={s.select}
            autoComplete="off"
          />
          <datalist id="devices-type-suggestions">
            {DEVICE_TYPE_SUGGESTIONS.map((suggestion) => (
              <option key={suggestion} value={suggestion} />
            ))}
          </datalist>
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
          {filtered && (
            <Button variant="quiet" onClick={clearFilters}>
              Clear filters
            </Button>
          )}
        </form>

        {devices.isError ? (
          <ErrorState
            error={devices.error}
            onRetry={() => void devices.refetch()}
            title="Devices could not be loaded"
          />
        ) : (
          <>
            <DataTable
              caption="Devices"
              columns={columns}
              rows={devices.data?.items ?? []}
              rowKey={(d) => d.id}
              loading={devices.isPending}
              empty={
                filtered ? (
                  <EmptyState
                    title="No devices match"
                    description="Try a different search, or clear the filters."
                    action={<Button onClick={clearFilters}>Clear filters</Button>}
                  />
                ) : can.registerDevice(user) ? (
                  <EmptyState
                    title="No devices yet"
                    description="Register the first device to start the record."
                    action={
                      <Button variant="primary" onClick={() => setRegistering(true)}>
                        Register a device
                      </Button>
                    }
                  />
                ) : (
                  <EmptyState
                    title="No devices with your unit yet"
                    description="Devices appear here once engineering hands them to your unit."
                  />
                )
              }
            />
            {devices.data && (
              <Pagination
                page={page}
                pageSize={DEVICES_PAGE_SIZE}
                total={devices.data.total}
                onPageChange={(next) => setParam("page", next > 1 ? String(next) : "")}
                noun="devices"
              />
            )}
          </>
        )}
      </Panel>

      <RegisterDeviceDialog open={registering} onOpenChange={setRegistering} />
    </>
  );
}
