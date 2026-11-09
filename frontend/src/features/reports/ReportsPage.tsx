import { Download, Printer } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Alert, ErrorState } from "@/components/ui/Feedback";
import { SelectField, TextField } from "@/components/ui/Fields";
import { PageHeader } from "@/components/ui/Layout";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/toastContext";
import { useUser } from "@/features/auth/authContext";
import { useUnits } from "@/features/units/queries";
import { lagosMonth } from "@/lib/format";
import { describeError } from "@/lib/messages";
import { can } from "@/lib/permissions";
import {
  isReportKey,
  MONTH_PATTERN,
  REPORTS,
  type ReportKey,
  type ReportParams,
} from "@/lib/reports";
import { downloadReport, useReport } from "./queries";
import s from "./ReportsPage.module.css";
import { ReportView } from "./ReportView";

export function ReportsPage() {
  const user = useUser();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [downloading, setDownloading] = useState<"xlsx" | "pdf" | null>(null);

  const rawKey = params.get("report");
  const key: ReportKey = isReportKey(rawKey) ? rawKey : "monthly-activity";
  const def = REPORTS.find((report) => report.key === key)!;

  const month = params.get("month") ?? lagosMonth();
  const min = Number(params.get("min")) || 3;
  const values: ReportParams = {
    month,
    from: params.get("from") ?? "",
    to: params.get("to") ?? "",
    min,
    include_recent: params.get("recent") === "yes",
    unit_id: can.filterByUnit(user) ? (params.get("unit") ?? "") : "",
  };

  const monthOk = !def.params.includes("month") || MONTH_PATTERN.test(month);
  const minOk = !def.params.includes("min") || (min >= 2 && min <= 100);
  const valid = monthOk && minOk;

  const hasSettings = def.params.length > 0 || can.filterByUnit(user);
  const units = useUnits(can.filterByUnit(user));
  const report = useReport(key, values, valid);

  function setParam(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  function pickReport(next: ReportKey) {
    // Each report has its own settings; the unit stays, so a unit's reports can be compared.
    const kept = new URLSearchParams();
    kept.set("report", next);
    const unit = params.get("unit");
    if (unit) kept.set("unit", unit);
    return `?${kept}`;
  }

  async function save(format: "xlsx" | "pdf") {
    setDownloading(format);
    try {
      const name = await downloadReport(key, values, format);
      toast.show({ title: "Download started", description: name });
    } catch (error) {
      toast.show({ title: "Could not download", description: describeError(error), tone: "error" });
    } finally {
      setDownloading(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle="Repair activity, worked out from the permanent record."
        actions={
          <>
            <Button
              icon={<Printer size={16} aria-hidden="true" />}
              onClick={() => window.print()}
              disabled={!report.data}
            >
              Print
            </Button>
            <Button
              icon={<Download size={16} aria-hidden="true" />}
              onClick={() => void save("xlsx")}
              loading={downloading === "xlsx"}
              disabled={!valid || downloading !== null}
            >
              Excel
            </Button>
            <Button
              icon={<Download size={16} aria-hidden="true" />}
              onClick={() => void save("pdf")}
              loading={downloading === "pdf"}
              disabled={!valid || downloading !== null}
            >
              PDF
            </Button>
          </>
        }
      />

      <nav aria-label="Choose a report" data-print="hide">
        <ul className={s.picker}>
          {REPORTS.map((item) => (
            <li key={item.key}>
              <Link
                to={pickReport(item.key)}
                className={s.pick}
                aria-current={item.key === key ? "page" : undefined}
                replace
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <p className={s.question}>{def.question}</p>

      {hasSettings && (
        <form
          className={s.filters}
          role="search"
          aria-label="Report settings"
          data-print="hide"
          onSubmit={(e) => e.preventDefault()}
        >
          {def.params.includes("month") && (
            <TextField
              label="Month"
              type="month"
              value={month}
              onChange={(e) => setParam("month", e.target.value)}
              fieldClassName={s.field}
              error={monthOk ? undefined : "Choose a month, for example 2026-10"}
            />
          )}
          {def.params.includes("range") && (
            <>
              <TextField
                label="From"
                type="date"
                value={values.from}
                onChange={(e) => setParam("from", e.target.value)}
                fieldClassName={s.field}
              />
              <TextField
                label="To"
                type="date"
                value={values.to}
                onChange={(e) => setParam("to", e.target.value)}
                fieldClassName={s.field}
              />
            </>
          )}
          {def.params.includes("min") && (
            <TextField
              label="At least this many repairs"
              type="number"
              min={2}
              max={100}
              value={String(min)}
              onChange={(e) => setParam("min", e.target.value)}
              fieldClassName={s.field}
              error={minOk ? undefined : "Choose 2 to 100"}
            />
          )}
          {def.params.includes("recent") && (
            <label className={s.check}>
              <input
                type="checkbox"
                checked={values.include_recent}
                onChange={(e) => setParam("recent", e.target.checked ? "yes" : "")}
              />
              Include answers that are not overdue yet
            </label>
          )}
          {can.filterByUnit(user) && (
            <SelectField
              label="Unit"
              value={values.unit_id}
              onChange={(e) => setParam("unit", e.target.value)}
              fieldClassName={s.field}
            >
              <option value="">All units</option>
              {units.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </SelectField>
          )}
          {def.params.includes("range") && !values.from && !values.to && (
            <p className={s.hint}>With no dates, the last 90 days are used.</p>
          )}
        </form>
      )}

      {!valid ? (
        <Alert tone="error">Check the settings above, then the report will appear.</Alert>
      ) : report.isError ? (
        <ErrorState
          error={report.error}
          onRetry={() => void report.refetch()}
          title="This report could not be produced"
        />
      ) : report.isPending ? (
        <Skeleton height="12rem" />
      ) : (
        <ReportView report={report.data} />
      )}

      <p className="print-only">
        Printed from the LASRRA Engineering Audit Register. Figures come from the permanent record
        and cannot be edited.
      </p>
    </>
  );
}
