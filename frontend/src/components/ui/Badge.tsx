import { AlertTriangle, Check, Clock, X } from "lucide-react";
import type { ReactNode } from "react";
import type { ComplaintStatus, DeviceStatus, PriorityLevel } from "@/api/types";
import { cx } from "@/lib/cx";
import {
  COMPLAINT_STATUS_LABEL,
  COMPLAINT_STATUS_TONE,
  DEVICE_STATUS_LABEL,
  DEVICE_STATUS_TONE,
  PRIORITY_LABEL,
  PRIORITY_TONE,
  type Tone,
} from "@/lib/labels";
import s from "./Badge.module.css";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx(s.badge, s[tone])}>{children}</span>;
}

export function StatusBadge({ status }: { status: DeviceStatus }) {
  return <Badge tone={DEVICE_STATUS_TONE[status]}>{DEVICE_STATUS_LABEL[status]}</Badge>;
}

export function ComplaintStatusBadge({ status }: { status: ComplaintStatus }) {
  return <Badge tone={COMPLAINT_STATUS_TONE[status]}>{COMPLAINT_STATUS_LABEL[status]}</Badge>;
}

export function PriorityBadge({ priority }: { priority: PriorityLevel }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{PRIORITY_LABEL[priority]}</Badge>;
}

export type StampState = "confirmed" | "disputed" | "pending" | "overdue";

const STAMP = {
  confirmed: { label: "Confirmed", Icon: Check },
  disputed: { label: "Disputed", Icon: X },
  pending: { label: "Pending", Icon: Clock },
  overdue: { label: "Overdue", Icon: AlertTriangle },
} as const;

/**
 * The unit's answer to a handover, drawn like a rubber stamp. Colour only reinforces it: the
 * word and the icon always say what it is.
 */
export function Stamp({ state, detail }: { state: StampState; detail?: string }) {
  const { label, Icon } = STAMP[state];
  return (
    <span className={cx(s.stamp, s[`stamp-${state}`])}>
      <Icon size={14} strokeWidth={2.5} aria-hidden="true" />
      <span>{label}</span>
      {detail && <span className={s.stampDetail}>{detail}</span>}
    </span>
  );
}
