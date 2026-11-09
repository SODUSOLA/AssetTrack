import type { EventType, TimelineEvent, User } from "@/api/types";
import { Stamp, type StampState } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { AcknowledgeTarget } from "@/features/acknowledgements/AcknowledgeDialog";
import { formatDate, formatDateTime, formatTime, plural } from "@/lib/format";
import { DEVICE_STATUS_LABEL, EVENT_LABEL } from "@/lib/labels";
import { can } from "@/lib/permissions";
import s from "./Timeline.module.css";

const PERSON_LABEL: Partial<Record<EventType, string>> = {
  assigned_to_unit: "Received by",
  received_for_repair: "Handed in by",
  returned_to_unit: "Collected by",
};

function stampFor(event: TimelineEvent): { state: StampState; detail?: string } | null {
  switch (event.ack_state) {
    case "confirmed":
      return { state: "confirmed" };
    case "disputed":
      return { state: "disputed" };
    case "pending": {
      const days = event.pending_days ?? 0;
      return {
        state: event.overdue ? "overdue" : "pending",
        detail: days === 0 ? "today" : plural(days, "day"),
      };
    }
    default:
      return null; // this kind of event is never acknowledged
  }
}

/** The unit's answer to one event, with Confirm and Dispute for the unit's own representative. */
function AckBlock({
  event,
  user,
  deviceTag,
  onAnswer,
}: {
  event: TimelineEvent;
  user: User;
  deviceTag: string;
  onAnswer: (target: AcknowledgeTarget) => void;
}) {
  const stamp = stampFor(event);
  if (!stamp) return null;
  const ack = event.acknowledgement;
  const base = { eventId: event.id, what: EVENT_LABEL[event.event_type], device: deviceTag };

  return (
    <div className={s.ack}>
      <Stamp state={stamp.state} {...(stamp.detail ? { detail: stamp.detail } : {})} />
      {ack ? (
        <div className={s.ackText}>
          <p>
            Acknowledged by <strong>{ack.acknowledged_by.full_name}</strong> on{" "}
            {formatDateTime(ack.acknowledged_at)}
          </p>
          {ack.comment && <blockquote className={s.quote}>{ack.comment}</blockquote>}
        </div>
      ) : (
        <div className={s.ackText}>
          <p>
            {event.overdue ? "Overdue: waiting" : "Waiting"} for {event.unit?.name ?? "the unit"} to
            answer
            {event.pending_days ? `. Pending since ${plural(event.pending_days, "day")}.` : "."}
          </p>
          {can.acknowledge(user, event.unit?.id) && (
            <div className={s.ackActions}>
              <Button
                size="sm"
                variant="primary"
                onClick={() => onAnswer({ ...base, mode: "confirm" })}
              >
                Confirm
              </Button>
              <Button size="sm" onClick={() => onAnswer({ ...base, mode: "dispute" })}>
                Dispute
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The audit view of one device: every recorded step with who did it, who it was handed to, what was
 * found, and whether the unit has acknowledged it. A ruled ledger, newest or oldest first.
 */
export function Timeline({
  events,
  user,
  deviceTag,
  order,
  onAnswer,
}: {
  events: TimelineEvent[];
  user: User;
  deviceTag: string;
  order: "newest" | "oldest";
  onAnswer: (target: AcknowledgeTarget) => void;
}) {
  const ordered = order === "newest" ? [...events].reverse() : events;

  return (
    <ol className={s.list} aria-label="Device timeline">
      {ordered.map((event) => {
        const person = PERSON_LABEL[event.event_type];
        const moved =
          event.from_status && event.from_status !== event.to_status
            ? `${DEVICE_STATUS_LABEL[event.from_status]} → ${DEVICE_STATUS_LABEL[event.to_status]}`
            : null;
        const titleId = `event-${event.id}`;
        return (
          <li key={event.id} className={s.entry}>
            <div className={s.when}>
              <time dateTime={event.occurred_at}>{formatDate(event.occurred_at)}</time>
              <span className={s.time}>{formatTime(event.occurred_at)}</span>
            </div>
            <span className={s.marker} aria-hidden="true" />
            <article className={s.card} aria-labelledby={titleId}>
              <header className={s.cardHeader}>
                <h3 id={titleId} className={s.title}>
                  {EVENT_LABEL[event.event_type]}
                </h3>
                <span className={`mono ${s.number}`}>#{event.id}</span>
              </header>
              {moved && <p className={s.moved}>{moved}</p>}

              <dl className={s.facts}>
                <div>
                  <dt>Recorded by</dt>
                  <dd>{event.actor.full_name}</dd>
                </div>
                {event.unit && (
                  <div>
                    <dt>Unit</dt>
                    <dd>{event.unit.name}</dd>
                  </div>
                )}
                {person && event.counterparty_name && (
                  <div>
                    <dt>{person}</dt>
                    <dd>{event.counterparty_name}</dd>
                  </div>
                )}
                {event.complaint && (
                  <div>
                    <dt>Complaint</dt>
                    <dd className="mono">{event.complaint.ticket_no}</dd>
                  </div>
                )}
              </dl>

              {event.diagnosis && (
                <div className={s.finding}>
                  <p className={s.findingLabel}>Diagnosis</p>
                  <p>{event.diagnosis}</p>
                </div>
              )}
              {event.notes && <p className={s.notes}>{event.notes}</p>}
              {event.corrects_event_id && (
                <p className={s.corrects}>
                  Corrects entry <span className="mono">#{event.corrects_event_id}</span>
                </p>
              )}

              <AckBlock event={event} user={user} deviceTag={deviceTag} onAnswer={onAnswer} />
            </article>
          </li>
        );
      })}
    </ol>
  );
}
