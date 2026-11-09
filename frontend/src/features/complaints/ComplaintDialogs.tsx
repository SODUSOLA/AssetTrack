import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import type { ComplaintDetail, PriorityLevel } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { SelectField, TextareaField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { useUser } from "@/features/auth/authContext";
import { useAssignableStaff } from "@/features/users/queries";
import { applyApiError } from "@/lib/forms";
import { PRIORITY_LABEL } from "@/lib/labels";
import { describeError } from "@/lib/messages";
import s from "./ComplaintForms.module.css";
import { useReopenComplaint, useUpdateComplaint } from "./queries";

type DialogProps = {
  complaint: ComplaintDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** Who works on the complaint. Naming someone also starts the work (open or reopened → in progress). */
export function AssignDialog({
  complaint,
  open,
  onOpenChange,
  anyone,
}: DialogProps & { anyone: boolean }) {
  const user = useUser();
  const toast = useToast();
  const update = useUpdateComplaint(complaint.id);
  const staff = useAssignableStaff(anyone && open);
  const [choice, setChoice] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const assignee = anyone ? choice : user.id;

  async function submit() {
    if (!assignee) {
      setProblem("Choose who will work on this complaint.");
      return;
    }
    setProblem(null);
    try {
      await update.mutateAsync({ assigned_to: assignee });
      toast.show({
        title: "Assigned",
        description: `${complaint.ticket_no} · ${anyone ? "work has started" : "you are on it"}`,
      });
      onOpenChange(false);
    } catch (error) {
      setProblem(describeError(error));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setProblem(null);
        onOpenChange(next);
      }}
      title={anyone ? "Assign this complaint" : "Take this complaint"}
      description={
        anyone
          ? "The person you choose is recorded as responsible, and the work is marked as started."
          : "You will be recorded as responsible, and the work is marked as started."
      }
      footer={
        <>
          <Button onClick={() => onOpenChange(false)} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" loading={update.isPending} onClick={() => void submit()}>
            {anyone ? "Assign" : "Take it"}
          </Button>
        </>
      }
    >
      {problem && <Alert tone="error">{problem}</Alert>}
      {anyone && (
        <div className={s.fields}>
          <SelectField
            label="Assign to"
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            disabled={staff.isPending}
          >
            <option value="">{staff.isPending ? "Loading people…" : "Choose a person"}</option>
            {staff.data?.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
                {person.role === "admin" ? " (Head of Engineering)" : ""}
              </option>
            ))}
          </SelectField>
          {staff.isError && <Alert tone="error">{describeError(staff.error)}</Alert>}
        </div>
      )}
    </Dialog>
  );
}

export function PriorityDialog({ complaint, open, onOpenChange }: DialogProps) {
  const toast = useToast();
  const update = useUpdateComplaint(complaint.id);
  const [priority, setPriority] = useState<PriorityLevel>(complaint.priority);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit() {
    setProblem(null);
    try {
      await update.mutateAsync({ priority });
      toast.show({ title: "Priority changed", description: complaint.ticket_no });
      onOpenChange(false);
    } catch (error) {
      setProblem(describeError(error));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Change the priority"
      description="The change is written into the complaint's history."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)} disabled={update.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={update.isPending}
            disabled={priority === complaint.priority}
            onClick={() => void submit()}
          >
            Save
          </Button>
        </>
      }
    >
      {problem && <Alert tone="error">{problem}</Alert>}
      <div className={s.fields}>
        <SelectField
          label="Priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value as PriorityLevel)}
        >
          {(Object.keys(PRIORITY_LABEL) as PriorityLevel[]).map((value) => (
            <option key={value} value={value}>
              {PRIORITY_LABEL[value]}
            </option>
          ))}
        </SelectField>
      </div>
    </Dialog>
  );
}

const noteSchema = z.object({
  note: z
    .string()
    .trim()
    .min(1, "Write a note: it is recorded permanently")
    .max(2000, "Keep this under 2000 characters"),
});
type NoteValues = z.infer<typeof noteSchema>;

export type NoteAction = "resolve" | "close" | "reopen";

const NOTE_COPY: Record<
  NoteAction,
  { title: string; description: string; label: string; submit: string; danger?: boolean }
> = {
  resolve: {
    title: "Mark as resolved",
    description:
      "Say what was done. The unit is then asked to confirm, and only the unit can close the complaint.",
    label: "What was done",
    submit: "Mark resolved",
  },
  close: {
    title: "Close without resolving",
    description:
      "Only for a duplicate or a mistaken complaint. It cannot be reopened by engineering.",
    label: "Why it is being closed",
    submit: "Close complaint",
    danger: true,
  },
  reopen: {
    title: "Reopen this complaint",
    description: "Say what is still wrong. The complaint goes back to engineering.",
    label: "What is still wrong",
    submit: "Reopen",
  },
};

/** Resolve, close or reopen: each needs a written reason, kept in the complaint's history. */
export function NoteDialog({
  complaint,
  action,
  onClose,
}: {
  complaint: ComplaintDetail;
  action: NoteAction | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const update = useUpdateComplaint(complaint.id);
  const reopen = useReopenComplaint(complaint.id);
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<NoteValues>({
    resolver: zodResolver(noteSchema),
    defaultValues: { note: "" },
  });
  const pending = update.isPending || reopen.isPending;
  const copy = action ? NOTE_COPY[action] : null;

  function close() {
    setProblem(null);
    form.reset();
    onClose();
  }

  async function onSubmit({ note }: NoteValues) {
    if (!action) return;
    setProblem(null);
    try {
      if (action === "resolve") await update.mutateAsync({ status: "resolved", comment: note });
      else if (action === "close") await update.mutateAsync({ status: "closed", comment: note });
      else await reopen.mutateAsync(note);
      toast.show({
        title:
          action === "resolve" ? "Marked resolved" : action === "close" ? "Closed" : "Reopened",
        description: complaint.ticket_no,
      });
      close();
    } catch (error) {
      setProblem(applyApiError(form, error));
    }
  }

  return (
    <Dialog
      open={action !== null}
      onOpenChange={(open) => !open && close()}
      title={copy?.title ?? ""}
      description={copy?.description}
      footer={
        <>
          <Button onClick={close} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant={copy?.danger ? "danger" : "primary"}
            type="submit"
            form="complaint-note"
            loading={pending}
          >
            {copy?.submit}
          </Button>
        </>
      }
    >
      <form id="complaint-note" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        {problem && <Alert tone="error">{problem}</Alert>}
        <div className={s.fields}>
          <TextareaField
            label={copy?.label ?? ""}
            autoFocus
            error={form.formState.errors.note?.message}
            {...form.register("note")}
          />
        </div>
      </form>
    </Dialog>
  );
}
