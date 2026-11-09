import { Plus } from "lucide-react";
import { useState } from "react";
import type { Unit } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/Layout";
import { Panel } from "@/components/ui/Panel";
import { useToast } from "@/components/ui/toastContext";
import { useUnits, useUpdateUnit } from "@/features/units/queries";
import { formatDate } from "@/lib/format";
import { describeError } from "@/lib/messages";
import s from "./Admin.module.css";
import { UnitFormDialog } from "./UnitFormDialog";

export function UnitsPage() {
  const units = useUnits();
  const update = useUpdateUnit();
  const toast = useToast();
  const [editing, setEditing] = useState<Unit | "new" | null>(null);
  const [toggling, setToggling] = useState<Unit | null>(null);

  const columns: Column<Unit>[] = [
    { id: "name", header: "Unit", primary: true, cell: (u) => u.name },
    { id: "code", header: "Code", cell: (u) => <span className="mono">{u.code}</span> },
    {
      id: "status",
      header: "Status",
      cell: (u) => (
        <Badge tone={u.is_active ? "success" : "neutral"}>
          {u.is_active ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    { id: "created", header: "Added", cell: (u) => formatDate(u.created_at) },
    {
      id: "actions",
      header: "Actions",
      cell: (u) => (
        <span className={s.rowActions}>
          <Button size="sm" onClick={() => setEditing(u)}>
            Edit
          </Button>
          <Button size="sm" onClick={() => setToggling(u)}>
            {u.is_active ? "Deactivate" : "Reactivate"}
          </Button>
        </span>
      ),
    },
  ];

  async function toggle() {
    if (!toggling) return;
    const next = !toggling.is_active;
    try {
      await update.mutateAsync({ id: toggling.id, body: { is_active: next } });
      toast.show({
        title: next ? "Unit reactivated" : "Unit deactivated",
        description: toggling.name,
      });
    } catch (error) {
      toast.show({
        title: "Could not change the unit",
        description: describeError(error),
        tone: "error",
      });
    } finally {
      setToggling(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Units"
        subtitle="The departments that receive devices and raise complaints."
        breadcrumbs={[{ label: "Administration" }, { label: "Units" }]}
        actions={
          <Button
            variant="primary"
            icon={<Plus size={16} aria-hidden="true" />}
            onClick={() => setEditing("new")}
          >
            Add a unit
          </Button>
        }
      />

      <Panel title="All units" flush>
        {units.isError ? (
          <ErrorState
            error={units.error}
            onRetry={() => void units.refetch()}
            title="Units could not be loaded"
          />
        ) : (
          <DataTable
            caption="Units"
            columns={columns}
            rows={units.data ?? []}
            rowKey={(u) => u.id}
            loading={units.isPending}
            empty={
              <EmptyState
                title="No units yet"
                description="Add the first unit, then register users and devices for it."
                action={
                  <Button variant="primary" onClick={() => setEditing("new")}>
                    Add a unit
                  </Button>
                }
              />
            }
          />
        )}
      </Panel>

      <UnitFormDialog
        key={editing === "new" || editing === null ? "new" : editing.id}
        unit={editing === "new" || editing === null ? undefined : editing}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
      />
      <ConfirmDialog
        open={toggling !== null}
        onOpenChange={(open) => !open && setToggling(null)}
        title={toggling?.is_active ? "Deactivate this unit?" : "Reactivate this unit?"}
        description={
          toggling?.is_active
            ? `${toggling.name} will no longer be offered when raising complaints or handing over devices. Its records stay exactly as they are.`
            : `${toggling?.name} will be offered again.`
        }
        confirmLabel={toggling?.is_active ? "Yes, deactivate" : "Yes, reactivate"}
        tone={toggling?.is_active ? "danger" : "primary"}
        loading={update.isPending}
        onConfirm={() => void toggle()}
      />
    </>
  );
}
