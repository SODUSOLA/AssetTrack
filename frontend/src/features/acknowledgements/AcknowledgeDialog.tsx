import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Alert } from "@/components/ui/Feedback";
import { TextareaField } from "@/components/ui/Fields";
import { useToast } from "@/components/ui/toastContext";
import { applyApiError } from "@/lib/forms";
import { describeError } from "@/lib/messages";
import { isApiError } from "@/api/errors";
import { useAcknowledge } from "./queries";

export type AcknowledgeTarget = {
  eventId: number;
  /** "Returned to unit" */
  what: string;
  /** "LAS-ENG-000007" */
  device: string;
  mode: "confirm" | "dispute";
};

const disputeSchema = z.object({
  comment: z
    .string()
    .trim()
    .min(1, "Say what is wrong, so engineering can respond")
    .max(2000, "Keep this under 2000 characters"),
});
type DisputeValues = z.infer<typeof disputeSchema>;

/**
 * A unit answers a handover once, and cannot take it back, so both answers ask first. A dispute
 * must say what is wrong: it is recorded permanently and engineering is asked to answer it.
 */
export function AcknowledgeDialog({
  target,
  onClose,
}: {
  target: AcknowledgeTarget | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const acknowledge = useAcknowledge();
  const [problem, setProblem] = useState<string | null>(null);
  const form = useForm<DisputeValues>({
    resolver: zodResolver(disputeSchema),
    defaultValues: { comment: "" },
  });

  function close() {
    setProblem(null);
    form.reset();
    onClose();
  }

  async function send(status: "confirmed" | "disputed", comment?: string) {
    if (!target) return;
    try {
      await acknowledge.mutateAsync({
        eventId: target.eventId,
        status,
        ...(comment ? { comment } : {}),
      });
      toast.show({
        title: status === "confirmed" ? "Confirmed" : "Dispute recorded",
        description: `${target.what} · ${target.device}`,
      });
      close();
    } catch (error) {
      if (isApiError(error) && error.code === "ALREADY_ACKNOWLEDGED") {
        toast.show({ title: "Already answered", description: describeError(error), tone: "error" });
        close();
        return;
      }
      setProblem(applyApiError(form, error));
    }
  }

  if (!target) return null;

  if (target.mode === "confirm") {
    return (
      <ConfirmDialog
        open
        onOpenChange={(open) => !open && close()}
        title="Confirm this handover?"
        description={
          <>
            You are confirming that <strong>{target.what.toLowerCase()}</strong> for{" "}
            <span className="mono">{target.device}</span> happened as recorded. You cannot change
            your answer afterwards.
            {problem && <Alert tone="error">{problem}</Alert>}
          </>
        }
        confirmLabel="Yes, confirm"
        loading={acknowledge.isPending}
        onConfirm={() => void send("confirmed")}
      />
    );
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && close()}
      title="Dispute this handover"
      description={
        <>
          Tell engineering what is wrong with <strong>{target.what.toLowerCase()}</strong> for{" "}
          <span className="mono">{target.device}</span>. Your answer is recorded permanently.
        </>
      }
      footer={
        <>
          <Button onClick={close} disabled={acknowledge.isPending}>
            Cancel
          </Button>
          <Button
            variant="danger"
            type="submit"
            form="dispute-form"
            loading={acknowledge.isPending}
          >
            Record dispute
          </Button>
        </>
      }
    >
      <form
        id="dispute-form"
        noValidate
        onSubmit={form.handleSubmit((values) => send("disputed", values.comment))}
      >
        {problem && <Alert tone="error">{problem}</Alert>}
        <TextareaField
          label="What is wrong?"
          autoFocus
          error={form.formState.errors.comment?.message}
          {...form.register("comment")}
        />
      </form>
    </Dialog>
  );
}
