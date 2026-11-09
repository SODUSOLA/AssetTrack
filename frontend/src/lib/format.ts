/** Dates and times are stored in UTC and always shown in Africa/Lagos (SPEC 1.5). */
const TIME_ZONE = "Africa/Lagos";
const LOCALE = "en-GB";

const dateFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const timeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateOnlyFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: "UTC",
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const isoDayFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** "05 Oct 2026" for an instant. */
export function formatDate(iso: string | null | undefined): string {
  return iso ? dateFormat.format(new Date(iso)) : "";
}

/** "14:30" for an instant. */
export function formatTime(iso: string | null | undefined): string {
  return iso ? timeFormat.format(new Date(iso)) : "";
}

/** "05 Oct 2026, 14:30". */
export function formatDateTime(iso: string | null | undefined): string {
  return iso ? `${formatDate(iso)}, ${formatTime(iso)}` : "";
}

/** A calendar date with no time ("2026-10-05"), which must not shift with the time zone. */
export function formatDateOnly(day: string | null | undefined): string {
  if (!day) return "";
  const [year, month, date] = day.split("-").map(Number);
  if (!year || !month || !date) return day;
  return dateOnlyFormat.format(new Date(Date.UTC(year, month - 1, date)));
}

/** Today's date in Lagos as YYYY-MM-DD. */
export function lagosToday(now: Date = new Date()): string {
  return isoDayFormat.format(now);
}

/** The current month in Lagos as YYYY-MM. */
export function lagosMonth(now: Date = new Date()): string {
  return lagosToday(now).slice(0, 7);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

const relativeFormat = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });

/** "3 days ago", "yesterday", "2 hours ago". */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const steps: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relativeFormat.format(Math.trunc(seconds / size), unit);
  }
  return "just now";
}
