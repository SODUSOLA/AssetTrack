import { Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { User, UserRole } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { SelectField } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Layout";
import { Pagination } from "@/components/ui/Pagination";
import { Panel } from "@/components/ui/Panel";
import { useToast } from "@/components/ui/toastContext";
import { useUser } from "@/features/auth/authContext";
import { useUnits } from "@/features/units/queries";
import { USERS_PAGE_SIZE, useUpdateUser, useUsers } from "@/features/users/queries";
import { ROLE_LABEL } from "@/lib/labels";
import { describeError } from "@/lib/messages";
import { generatePassword } from "@/lib/password";
import s from "./Admin.module.css";
import { PasswordReveal } from "./PasswordReveal";
import { UserFormDialog, type Created } from "./UserFormDialog";

const ROLES = Object.keys(ROLE_LABEL) as UserRole[];

type Revealed = { name: string; email: string; password: string; reason: "created" | "reset" };

export function UsersPage() {
  const me = useUser();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [toggling, setToggling] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [revealed, setRevealed] = useState<Revealed | null>(null);

  const page = Math.max(1, Number(params.get("page")) || 1);
  const role = (params.get("role") as UserRole | null) ?? undefined;
  const status = params.get("status");
  const is_active = status === "active" ? true : status === "inactive" ? false : undefined;

  const users = useUsers({
    page,
    ...(role ? { role } : {}),
    ...(is_active !== undefined ? { is_active } : {}),
  });
  const units = useUnits();
  const update = useUpdateUser();
  const unitName = new Map((units.data ?? []).map((u) => [u.id, u.name]));

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  const columns: Column<User>[] = [
    {
      id: "name",
      header: "Name",
      primary: true,
      cell: (u) => (
        <>
          {u.full_name}
          {u.id === me.id && <span className={s.you}>You</span>}
          <span className={s.sub}>{u.email}</span>
        </>
      ),
    },
    { id: "role", header: "Role", cell: (u) => ROLE_LABEL[u.role] },
    {
      id: "unit",
      header: "Unit",
      cell: (u) => (u.unit_id ? (unitName.get(u.unit_id) ?? "…") : "-"),
    },
    {
      id: "status",
      header: "Status",
      cell: (u) => (
        <Badge tone={u.is_active ? "success" : "neutral"}>
          {u.is_active ? "Active" : "Deactivated"}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "Actions",
      cell: (u) => (
        <span className={s.rowActions}>
          <Button size="sm" onClick={() => setEditing(u)}>
            Edit
          </Button>
          <Button size="sm" onClick={() => setResetting(u)}>
            Reset password
          </Button>
          {u.id !== me.id && (
            <Button size="sm" onClick={() => setToggling(u)}>
              {u.is_active ? "Deactivate" : "Reactivate"}
            </Button>
          )}
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
        title: next ? "Account reactivated" : "Account deactivated",
        description: toggling.full_name,
      });
    } catch (error) {
      toast.show({
        title: "Could not change the account",
        description: describeError(error),
        tone: "error",
      });
    } finally {
      setToggling(null);
    }
  }

  async function reset() {
    if (!resetting) return;
    const target = resetting;
    const password = generatePassword();
    try {
      await update.mutateAsync({ id: target.id, body: { password } });
      setResetting(null);
      setRevealed({ name: target.full_name, email: target.email, password, reason: "reset" });
    } catch (error) {
      setResetting(null);
      toast.show({
        title: "Could not reset the password",
        description: describeError(error),
        tone: "error",
      });
    }
  }

  function onCreated({ user, password }: Created) {
    setRevealed({ name: user.full_name, email: user.email, password, reason: "created" });
  }

  const filtered = !!(role || is_active !== undefined);

  return (
    <>
      <PageHeader
        title="People"
        subtitle={
          users.data ? `${users.data.total} ${filtered ? "matching people" : "people"}` : undefined
        }
        breadcrumbs={[{ label: "Administration" }, { label: "People" }]}
        actions={
          <Button
            variant="primary"
            icon={<Plus size={16} aria-hidden="true" />}
            onClick={() => setEditing("new")}
          >
            Add a person
          </Button>
        }
      />

      <Panel title="All people" flush>
        <form
          className={s.filters}
          role="search"
          aria-label="Filter people"
          onSubmit={(e) => e.preventDefault()}
        >
          <SelectField
            label="Role"
            value={role ?? ""}
            onChange={(e) => setParam("role", e.target.value)}
            fieldClassName={s.select}
          >
            <option value="">Any role</option>
            {ROLES.map((value) => (
              <option key={value} value={value}>
                {ROLE_LABEL[value]}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Status"
            value={status ?? ""}
            onChange={(e) => setParam("status", e.target.value)}
            fieldClassName={s.select}
          >
            <option value="">Active and deactivated</option>
            <option value="active">Active</option>
            <option value="inactive">Deactivated</option>
          </SelectField>
          {filtered && (
            <Button variant="quiet" onClick={() => setParams({}, { replace: true })}>
              Clear filters
            </Button>
          )}
        </form>

        {users.isError ? (
          <ErrorState
            error={users.error}
            onRetry={() => void users.refetch()}
            title="People could not be loaded"
          />
        ) : (
          <>
            <DataTable
              caption="People"
              columns={columns}
              rows={users.data?.items ?? []}
              rowKey={(u) => u.id}
              loading={users.isPending}
              cardsBelow={820}
              empty={
                <EmptyState
                  title="No one matches"
                  description="Try different filters, or clear them."
                />
              }
            />
            {users.data && (
              <Pagination
                page={users.data.page}
                pageSize={USERS_PAGE_SIZE}
                total={users.data.total}
                onPageChange={(next) => setParam("page", String(next))}
                noun="people"
              />
            )}
          </>
        )}
      </Panel>

      <UserFormDialog
        key={editing === "new" || editing === null ? "new" : editing.id}
        user={editing === "new" || editing === null ? undefined : editing}
        isSelf={editing !== "new" && editing !== null && editing.id === me.id}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        onCreated={onCreated}
      />

      <ConfirmDialog
        open={toggling !== null}
        onOpenChange={(open) => !open && setToggling(null)}
        title={toggling?.is_active ? "Deactivate this account?" : "Reactivate this account?"}
        description={
          toggling?.is_active
            ? `${toggling.full_name} will be signed out everywhere and will not be able to sign in. Everything they recorded stays in the record: accounts are never deleted.`
            : `${toggling?.full_name} will be able to sign in again.`
        }
        confirmLabel={toggling?.is_active ? "Yes, deactivate" : "Yes, reactivate"}
        tone={toggling?.is_active ? "danger" : "primary"}
        loading={update.isPending}
        onConfirm={() => void toggle()}
      />
      <ConfirmDialog
        open={resetting !== null}
        onOpenChange={(open) => !open && setResetting(null)}
        title="Reset this password?"
        description={`${resetting?.full_name} will be signed out everywhere, and a new password will be shown here once for you to pass on.`}
        confirmLabel="Yes, reset it"
        loading={update.isPending}
        onConfirm={() => void reset()}
      />
      {revealed && <PasswordReveal open onClose={() => setRevealed(null)} {...revealed} />}
    </>
  );
}
