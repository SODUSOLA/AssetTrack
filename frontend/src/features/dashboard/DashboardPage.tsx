import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ButtonLink } from "@/components/ui/Button";
import { EmptyState, ErrorState } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/Layout";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/Skeleton";
import { Stamp } from "@/components/ui/Badge";
import { useUser } from "@/features/auth/authContext";
import { usePendingAcknowledgements } from "@/features/acknowledgements/queries";
import { useRecentEvents } from "@/features/events/queries";
import {
  sectionRows,
  summaryOf,
  useAwaitingUnitReport,
  useMonthlyActivityReport,
  useOpenTicketsReport,
} from "@/features/reports/queries";
import { cx } from "@/lib/cx";
import { formatDate, formatRelative, lagosMonth, plural } from "@/lib/format";
import { EVENT_LABEL, ROLE_LABEL } from "@/lib/labels";
import s from "./DashboardPage.module.css";

function Figure({
  label,
  value,
  note,
  alert = false,
  loading,
  to,
}: {
  label: string;
  value: number | string | null | undefined;
  note?: ReactNode;
  /** Something needs attention: the figure is drawn in the alert colour. */
  alert?: boolean;
  loading: boolean;
  /** Where the full list for this figure is. */
  to?: string;
}) {
  return (
    <div className={cx(s.figure, alert && s.alert)}>
      <dt className={s.figureLabel}>{to ? <Link to={to}>{label}</Link> : label}</dt>
      <dd className={s.figureValue}>
        {loading ? <Skeleton width="3rem" height="2rem" /> : (value ?? "0")}
      </dd>
      {note && <dd className={s.figureNote}>{note}</dd>}
    </div>
  );
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}
/** Report cells are lower-case phrases ("received for repair"); show them as sentences. */
function sentence(value: unknown): string {
  const s = text(value);
  return s.charAt(0).toUpperCase() + s.slice(1);
}
function count(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

export function DashboardPage() {
  const user = useUser();
  const isRep = user.role === "unit_rep";

  const tickets = useOpenTicketsReport();
  const awaiting = useAwaitingUnitReport();
  const monthly = useMonthlyActivityReport(lagosMonth());
  const events = useRecentEvents();
  const pending = usePendingAcknowledgements({ page: 1, page_size: 5 });

  const ticketFigures = summaryOf(tickets.data);
  const awaitingFigures = summaryOf(awaiting.data);
  const monthFigures = summaryOf(monthly.data);
  const unitName = isRep ? tickets.data?.scope.label : undefined;
  const firstName = user.full_name.split(" ")[0];

  const overdueRows = sectionRows(awaiting.data, "pending").slice(0, 5);
  const disputeRows = sectionRows(awaiting.data, "disputes").slice(0, 5);
  const urgent = count(ticketFigures.urgent);

  return (
    <>
      <PageHeader
        title={`Welcome, ${firstName}`}
        subtitle={[ROLE_LABEL[user.role], unitName].filter(Boolean).join(" · ")}
      />

      <dl className={s.figures} aria-label="Key figures">
        <Figure
          label="Open tickets"
          to="/complaints"
          value={count(ticketFigures.open)}
          note={urgent > 0 ? `${urgent} critical or high priority` : "None urgent"}
          alert={urgent > 0}
          loading={tickets.isPending}
        />
        <Figure
          label="In the workshop"
          to="/reports?report=monthly-activity"
          value={count(monthFigures.in_workshop)}
          note="Being repaired, or waiting to be collected"
          loading={monthly.isPending}
        />
        {isRep ? (
          <Figure
            label="Waiting for you"
            to="/acknowledgements"
            value={pending.data?.total ?? 0}
            note="Handovers to confirm or dispute"
            alert={(pending.data?.total ?? 0) > 0}
            loading={pending.isPending}
          />
        ) : (
          <>
            <Figure
              label="Overdue answers"
              to="/acknowledgements?overdue=yes"
              value={count(awaitingFigures.overdue_acknowledgements)}
              note="Units that have not yet answered"
              alert={count(awaitingFigures.overdue_acknowledgements) > 0}
              loading={awaiting.isPending}
            />
            <Figure
              label="Unanswered disputes"
              value={count(awaitingFigures.open_disputes)}
              note="Waiting for engineering"
              alert={count(awaitingFigures.open_disputes) > 0}
              loading={awaiting.isPending}
            />
          </>
        )}
      </dl>

      <div className={s.columns}>
        {isRep ? (
          <Panel
            title="Waiting for you"
            actions={
              <ButtonLink to="/acknowledgements" size="sm">
                See all
              </ButtonLink>
            }
          >
            {pending.isError ? (
              <ErrorState error={pending.error} onRetry={() => void pending.refetch()} />
            ) : pending.isPending ? (
              <Skeleton height="4rem" />
            ) : pending.data.items.length === 0 ? (
              <EmptyState
                title="You are all caught up"
                description="Nothing is waiting for your answer."
              />
            ) : (
              <ul className={s.list}>
                {pending.data.items.map((item) => (
                  <li key={item.event_id} className={s.item}>
                    <div>
                      <p className={s.itemTitle}>
                        {EVENT_LABEL[item.event_type]} ·{" "}
                        <Link to={`/devices/${item.device.id}`} className="mono">
                          {item.device.asset_tag}
                        </Link>
                      </p>
                      <p className={s.itemMeta}>
                        {formatDate(item.occurred_at)} · {item.device.device_type}
                      </p>
                    </div>
                    <Stamp
                      state={item.overdue ? "overdue" : "pending"}
                      detail={plural(item.pending_days, "day")}
                    />
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        ) : (
          <Panel
            title="Needs attention"
            actions={
              <ButtonLink to="/acknowledgements" size="sm">
                All pending
              </ButtonLink>
            }
          >
            {awaiting.isError ? (
              <ErrorState error={awaiting.error} onRetry={() => void awaiting.refetch()} />
            ) : awaiting.isPending ? (
              <Skeleton height="4rem" />
            ) : overdueRows.length + disputeRows.length === 0 ? (
              <EmptyState
                title="Nothing is overdue"
                description="Every handover has been answered or is still within the time allowed."
              />
            ) : (
              <>
                {overdueRows.length > 0 && (
                  <>
                    <h3 className={s.subhead}>Waiting for a unit to answer</h3>
                    <ul className={s.list}>
                      {overdueRows.map((row) => (
                        <li key={count(row.event_id)} className={s.item}>
                          <div>
                            <p className={s.itemTitle}>
                              {sentence(row.event)} ·{" "}
                              <Link
                                to={`/devices?q=${encodeURIComponent(text(row.asset_tag))}`}
                                className="mono"
                              >
                                {text(row.asset_tag)}
                              </Link>
                            </p>
                            <p className={s.itemMeta}>{text(row.unit)}</p>
                          </div>
                          <Stamp state="overdue" detail={plural(count(row.days_pending), "day")} />
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {disputeRows.length > 0 && (
                  <>
                    <h3 className={s.subhead}>Disputes to answer</h3>
                    <ul className={s.list}>
                      {disputeRows.map((row) => (
                        <li key={count(row.event_id)} className={s.item}>
                          <div>
                            <p className={s.itemTitle}>
                              {text(row.unit)} ·{" "}
                              <Link
                                to={`/devices?q=${encodeURIComponent(text(row.asset_tag))}`}
                                className="mono"
                              >
                                {text(row.asset_tag)}
                              </Link>
                            </p>
                            <p className={s.itemMeta}>“{text(row.comment)}”</p>
                          </div>
                          <Stamp state="disputed" detail={plural(count(row.days_open), "day")} />
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
          </Panel>
        )}

        <Panel title="Latest activity">
          {events.isError ? (
            <ErrorState error={events.error} onRetry={() => void events.refetch()} />
          ) : events.isPending ? (
            <Skeleton height="6rem" />
          ) : events.data.items.length === 0 ? (
            <EmptyState
              title="No activity yet"
              description="Handovers and repairs will appear here as they are recorded."
            />
          ) : (
            <ul className={s.list}>
              {events.data.items.map((event) => (
                <li key={event.id} className={s.item}>
                  <div>
                    <p className={s.itemTitle}>
                      {EVENT_LABEL[event.event_type]} ·{" "}
                      <Link to={`/devices/${event.device.id}`} className="mono">
                        {event.device.asset_tag}
                      </Link>
                    </p>
                    <p className={s.itemMeta}>
                      {event.actor.full_name}
                      {event.unit ? ` · ${event.unit.name}` : ""}
                    </p>
                  </div>
                  <time className={s.when} dateTime={event.occurred_at}>
                    {formatRelative(event.occurred_at)}
                  </time>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
