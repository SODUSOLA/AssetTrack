import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Flag, UserPlus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";
import { isApiError } from "@/api/errors";
import type { ComplaintDetail, ComplaintStatus } from "@/api/types";
import { ComplaintStatusBadge, PriorityBadge, Stamp, type StampState } from "@/components/ui/Badge";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Alert, EmptyState, ErrorState } from "@/components/ui/Feedback";
import { TextareaField } from "@/components/ui/Fields";
import { DefinitionList, PageHeader } from "@/components/ui/Layout";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/toastContext";
import { useUser } from "@/features/auth/authContext";
import { cx } from "@/lib/cx";
import { formatDate, formatDateTime } from "@/lib/format";
import { applyApiError } from "@/lib/forms";
import { CATEGORY_LABEL, EVENT_LABEL } from "@/lib/labels";
import { describeError } from "@/lib/messages";
import { AssignDialog, NoteDialog, PriorityDialog, type NoteAction } from "./ComplaintDialogs";
import s from "./ComplaintDetailPage.module.css";
import { useAddComment, useComplaint, useConfirmComplaint } from "./queries";
import { awaitsDeviceAnswer, complaintActions, STATUS_STEPS } from "./rules";

/** Where the ticket is on its normal way to closed. Text says it; the bar only reinforces it. */
function Progress({ status }: { status: ComplaintStatus }) {
  // "Reopened" is a way back into the work, so it counts as being at the start.
  const at = status === "reopened" ? 0 : STATUS_STEPS.indexOf(status);
  return (
    <>
      <ol className={s.steps} aria-label="Progress">
        {STATUS_STEPS.map((step, index) => (
          <li
            key={step}
            className={cx(s.step, index < at && s.done, index === at && s.current)}
            aria-current={index === at ? "step" : undefined}
          >
            <span>{index < at ? "Done" : index === at ? "Now" : "Next"}</span>
            {step === "open"
              ? "Raised"
              : step === "in_progress"
                ? "In progress"
                : step === "resolved"
                  ? "Resolved"
                  : "Closed"}
          </li>
        ))}
      </ol>
      {status === "reopened" && (
        <p className={s.stepNote}>
          Reopened: the unit says the problem is not fixed, so it is back with engineering.
        </p>
      )}
    </>
  );
}

const commentSchema = z.object({
  body: z
    .string()
    .trim()
    .min(1, "Write something first")
    .max(2000, "Keep this under 2000 characters"),
});
type CommentValues = z.infer<typeof commentSchema>;

function AddComment({ id }: { id: string }) {
  const add = useAddComment(id);
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<CommentValues>({
    resolver: zodResolver(commentSchema),
    defaultValues: { body: "" },
  });

  async function onSubmit({ body }: CommentValues) {
    setProblem(null);
    try {
      await add.mutateAsync(body);
      form.reset();
    } catch (error) {
      setProblem(applyApiError(form, error));
    }
  }

  return (
    <form className={s.addComment} noValidate onSubmit={form.handleSubmit(onSubmit)}>
      {problem && <Alert tone="error">{problem}</Alert>}
      <TextareaField
        label="Add a comment"
        rows={3}
        hint="Everyone involved, including the unit, can read it. It cannot be edited or removed."
        error={form.formState.errors.body?.message}
        {...form.register("body")}
      />
      <div className={s.addActions}>
        <Button variant="primary" type="submit" loading={add.isPending}>
          Post comment
        </Button>
      </div>
    </form>
  );
}

function ackStamp(state: string, overdue: boolean): StampState | null {
  if (state === "confirmed" || state === "disputed") return state;
  if (state === "pending") return overdue ? "overdue" : "pending";
  return null;
}

function Thread({ complaint }: { complaint: ComplaintDetail }) {
  return complaint.comments.length === 0 ? (
    <EmptyState title="No comments yet" description="Changes and replies will appear here." />
  ) : (
    <ol className={s.thread} aria-label="Comments, oldest first">
      {complaint.comments.map((comment) => (
        <li key={comment.id} className={comment.is_system ? `${s.comment} ${s.system}` : s.comment}>
          <p className={s.meta}>
            <span className={s.author}>{comment.author.full_name}</span>
            {comment.is_system && <span>recorded a change</span>}
            <time dateTime={comment.created_at}>{formatDateTime(comment.created_at)}</time>
          </p>
          <p className={s.body}>{comment.body}</p>
        </li>
      ))}
    </ol>
  );
}

export function ComplaintDetailPage() {
  const { complaintId = "" } = useParams();
  const user = useUser();
  const toast = useToast();
  const complaint = useComplaint(complaintId);
  const confirm = useConfirmComplaint(complaintId);

  const [assigning, setAssigning] = useState(false);
  const [prioritising, setPrioritising] = useState(false);
  const [note, setNote] = useState<NoteAction | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  if (complaint.isError) {
    if (isApiError(complaint.error) && complaint.error.status === 404) {
      return (
        <>
          <PageHeader
            title="Complaint not found"
            breadcrumbs={[{ label: "Complaints", to: "/complaints" }, { label: "Not found" }]}
          />
          <EmptyState
            title="There is no such complaint"
            description="It may have been typed wrongly, or it belongs to another unit."
            action={
              <ButtonLink to="/complaints" variant="primary">
                Back to complaints
              </ButtonLink>
            }
          />
        </>
      );
    }
    return (
      <ErrorState
        error={complaint.error}
        onRetry={() => void complaint.refetch()}
        title="This complaint could not be loaded"
      />
    );
  }

  const c = complaint.data;
  const actions = c ? complaintActions(user, c) : null;
  const waitingOnDevice = !!c && awaitsDeviceAnswer(c);
  // An engineer can only take a complaint for themselves, so there is nothing to offer once they have.
  const assignLabel =
    c && actions?.assign
      ? actions.assignAnyone
        ? c.assigned_to
          ? "Reassign"
          : "Assign"
        : c.assigned_to?.id === user.id
          ? null
          : "Take it"
      : null;

  async function onConfirm() {
    setProblem(null);
    try {
      await confirm.mutateAsync();
      setConfirming(false);
      toast.show({ title: "Complaint closed", description: c?.ticket_no });
    } catch (error) {
      setConfirming(false);
      setProblem(describeError(error));
    }
  }

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: "Complaints", to: "/complaints" },
          { label: c?.ticket_no ?? "Complaint" },
        ]}
        title={
          c ? <span className="mono">{c.ticket_no}</span> : <Skeleton width="12rem" height="2rem" />
        }
        subtitle={c?.title}
        actions={
          c &&
          actions && (
            <>
              {assignLabel && (
                <Button
                  icon={<UserPlus size={16} aria-hidden="true" />}
                  onClick={() => setAssigning(true)}
                >
                  {assignLabel}
                </Button>
              )}
              {actions.prioritise && (
                <Button
                  icon={<Flag size={16} aria-hidden="true" />}
                  onClick={() => setPrioritising(true)}
                >
                  Priority
                </Button>
              )}
              {actions.close && <Button onClick={() => setNote("close")}>Close</Button>}
              {actions.resolve && (
                <Button
                  variant="primary"
                  icon={<Check size={16} aria-hidden="true" />}
                  onClick={() => setNote("resolve")}
                >
                  Mark resolved
                </Button>
              )}
              {actions.reopen && !waitingOnDevice && (
                <Button onClick={() => setNote("reopen")}>Reopen</Button>
              )}
              {actions.confirm && !waitingOnDevice && (
                <Button variant="primary" onClick={() => setConfirming(true)}>
                  Confirm it is fixed
                </Button>
              )}
            </>
          )
        }
      />

      {problem && <Alert tone="error">{problem}</Alert>}
      {waitingOnDevice && c && (
        <Alert tone="info">
          The returned device is waiting for {c.unit.name} to answer.{" "}
          {c.device && <Link to={`/devices/${c.device.id}`}>Answer on the device</Link>}
          {c.device ? ": that closes or reopens this complaint." : "."}
        </Alert>
      )}

      <div className={s.grid}>
        <div className={s.column}>
          <Panel title="Progress">
            {c ? <Progress status={c.status} /> : <Skeleton height="3rem" />}
          </Panel>

          <Panel title="What was reported">
            {c ? <p className={s.description}>{c.description}</p> : <Skeleton height="4rem" />}
          </Panel>

          <Panel title="Comments and history">
            {c ? (
              <>
                <Thread complaint={c} />
                {actions?.comment && <AddComment id={c.id} />}
              </>
            ) : (
              <Skeleton height="6rem" />
            )}
          </Panel>
        </div>

        <div className={s.column}>
          <Panel title="Details">
            {!c ? (
              <Skeleton height="8rem" />
            ) : (
              <DefinitionList
                items={[
                  { label: "Status", value: <ComplaintStatusBadge status={c.status} /> },
                  { label: "Priority", value: <PriorityBadge priority={c.priority} /> },
                  { label: "Unit", value: c.unit.name },
                  {
                    label: "Device",
                    value: c.device ? (
                      <Link to={`/devices/${c.device.id}`} className="mono">
                        {c.device.asset_tag}
                      </Link>
                    ) : (
                      "Not linked yet"
                    ),
                  },
                  { label: "Kind of problem", value: CATEGORY_LABEL[c.category] },
                  { label: "Raised by", value: c.raised_by.full_name },
                  { label: "Assigned to", value: c.assigned_to?.full_name ?? "Nobody yet" },
                  { label: "Raised", value: formatDateTime(c.created_at) },
                  {
                    label: "Resolved",
                    value: c.resolved_at ? formatDateTime(c.resolved_at) : "Not yet",
                  },
                  { label: "Closed", value: c.closed_at ? formatDateTime(c.closed_at) : "Not yet" },
                ]}
              />
            )}
          </Panel>

          <Panel title="Device events for this complaint">
            {!c ? (
              <Skeleton height="4rem" />
            ) : c.events.length === 0 ? (
              <EmptyState
                title="No device events yet"
                description="Steps on the device, such as taking it in, appear here."
              />
            ) : (
              <ol className={s.events}>
                {[...c.events].reverse().map((event) => {
                  const stamp = ackStamp(event.ack_state, event.overdue);
                  return (
                    <li key={event.id} className={s.event}>
                      <span>
                        {EVENT_LABEL[event.event_type]}
                        <span className={s.eventSub}>
                          {formatDate(event.occurred_at)}
                          {c.device && (
                            <>
                              {" "}
                              ·{" "}
                              <Link to={`/devices/${c.device.id}`} className="mono">
                                {c.device.asset_tag}
                              </Link>
                            </>
                          )}
                        </span>
                      </span>
                      {stamp && <Stamp state={stamp} />}
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>
        </div>
      </div>

      {c && actions && (
        <>
          {actions.assign && (
            <AssignDialog
              complaint={c}
              open={assigning}
              onOpenChange={setAssigning}
              anyone={actions.assignAnyone}
            />
          )}
          {actions.prioritise && (
            <PriorityDialog complaint={c} open={prioritising} onOpenChange={setPrioritising} />
          )}
          <NoteDialog complaint={c} action={note} onClose={() => setNote(null)} />
          <ConfirmDialog
            open={confirming}
            onOpenChange={setConfirming}
            title="Confirm that it is fixed?"
            description={`${c.ticket_no} will be closed. You cannot reopen a closed complaint, so raise a new one if the fault returns.`}
            confirmLabel="Yes, it is fixed"
            loading={confirm.isPending}
            onConfirm={() => void onConfirm()}
          />
        </>
      )}
    </>
  );
}
