import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Alert } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import s from "./Admin.module.css";

/**
 * The starting password, shown once. It is not kept anywhere: when this closes, it is gone, and
 * the only remedy is to reset the password again.
 */
export function PasswordReveal({
  open,
  onClose,
  name,
  email,
  password,
  reason,
}: {
  open: boolean;
  onClose: () => void;
  name: string;
  email: string;
  password: string;
  reason: "created" | "reset";
}) {
  const [copied, setCopied] = useState<boolean | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      setCopied(false); // clipboard blocked: the password is selectable on screen
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setCopied(null);
          onClose();
        }
      }}
      title={reason === "created" ? "Account created" : "Password reset"}
      description={
        reason === "created"
          ? `${name} can sign in as ${email} with this password.`
          : `${name} was signed out everywhere. They can sign in again with this password.`
      }
      footer={
        <Button variant="primary" onClick={onClose}>
          I have passed it on
        </Button>
      }
    >
      <div className={s.secret}>
        <span className={s.secretValue} data-testid="one-time-password">
          {password}
        </span>
        <Button
          size="sm"
          icon={
            copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />
          }
          onClick={() => void copy()}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {copied === false && (
        <Alert tone="info">
          Your browser did not allow copying. Select the password and copy it.
        </Alert>
      )}
      <Alert tone="info">
        This is the only time it is shown. Ask {name} to change it under Your account after signing
        in.
      </Alert>
    </Dialog>
  );
}
