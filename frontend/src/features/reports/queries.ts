import { useQuery } from "@tanstack/react-query";
import { api, authedFetch, unwrap } from "@/api/client";
import { errorFromResponse, networkError } from "@/api/errors";
import type { Report } from "@/api/types";
import { fileName, queryFor, type ReportKey, type ReportParams } from "@/lib/reports";

const BASE = import.meta.env.VITE_API_BASE ?? "";

/** The headline figures of a report by key, and a section's rows by key. */
export function summaryOf(report: Report | undefined): Record<string, number | string | null> {
  return Object.fromEntries((report?.summary ?? []).map((item) => [item.key, item.value]));
}

export function sectionRows(
  report: Report | undefined,
  key: string,
): Array<Record<string, unknown>> {
  return report?.sections.find((section) => section.key === key)?.rows ?? [];
}

export function useOpenTicketsReport() {
  return useQuery({
    queryKey: ["reports", "open-tickets"],
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/reports/open-tickets", { signal })),
  });
}

export function useAwaitingUnitReport() {
  return useQuery({
    queryKey: ["reports", "awaiting-unit"],
    queryFn: ({ signal }) => unwrap(api.GET("/api/v1/reports/awaiting-unit", { signal })),
  });
}

/** For the current month, "in the workshop at month end" is simply "in the workshop now". */
export function useMonthlyActivityReport(month: string) {
  return useQuery({
    queryKey: ["reports", "monthly-activity", month],
    queryFn: ({ signal }) =>
      unwrap(api.GET("/api/v1/reports/monthly-activity", { params: { query: { month } }, signal })),
  });
}

/** Any one of the five reports, as JSON. Each report has its own typed call. */
function fetchReport(key: ReportKey, params: ReportParams, signal: AbortSignal): Promise<Report> {
  const unit_id = params.unit_id || undefined;
  switch (key) {
    case "monthly-activity":
      return unwrap(
        api.GET("/api/v1/reports/monthly-activity", {
          params: { query: { month: params.month ?? "", unit_id } },
          signal,
        }),
      );
    case "open-tickets":
      return unwrap(
        api.GET("/api/v1/reports/open-tickets", { params: { query: { unit_id } }, signal }),
      );
    case "turnaround":
      return unwrap(
        api.GET("/api/v1/reports/turnaround", {
          params: {
            query: { from: params.from || undefined, to: params.to || undefined, unit_id },
          },
          signal,
        }),
      );
    case "repeat-faults":
      return unwrap(
        api.GET("/api/v1/reports/repeat-faults", {
          params: {
            query: {
              from: params.from || undefined,
              to: params.to || undefined,
              min: params.min,
              unit_id,
            },
          },
          signal,
        }),
      );
    case "awaiting-unit":
      return unwrap(
        api.GET("/api/v1/reports/awaiting-unit", {
          params: { query: { include_recent: params.include_recent || undefined, unit_id } },
          signal,
        }),
      );
  }
}

export function useReport(key: ReportKey, params: ReportParams, enabled = true) {
  return useQuery({
    queryKey: ["reports", "view", key, params],
    enabled,
    queryFn: ({ signal }) => fetchReport(key, params, signal),
  });
}

/**
 * Fetch an Excel or PDF file through the signed-in client (a plain link could not carry the
 * token) and hand it to the browser to save. Nothing is kept afterwards.
 */
export async function downloadReport(
  key: ReportKey,
  params: ReportParams,
  format: "xlsx" | "pdf",
): Promise<string> {
  const query = new URLSearchParams(
    Object.entries({ ...queryFor(key, params), format }).map(([k, v]) => [k, String(v)]),
  );
  let response: Response;
  try {
    response = await authedFetch(new Request(`${BASE}/api/v1/reports/${key}?${query}`));
  } catch (cause) {
    throw networkError(cause);
  }
  if (!response.ok) throw await errorFromResponse(response);

  const blob = await response.blob();
  const name =
    /filename="?([^";]+)"?/.exec(response.headers.get("content-disposition") ?? "")?.[1] ??
    fileName(key, params, format);
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    // Give the browser a moment to start the save before the object is released.
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
  return name;
}
