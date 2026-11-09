import { useCallback, useState, useSyncExternalStore, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import s from "./DataTable.module.css";
import { Skeleton } from "./Skeleton";

/** True while the element is narrower than `below` pixels. Tables render as a table where this cannot be measured. */
function useCards(below: number) {
  // A callback ref (kept in state), so measuring starts whenever the element appears, even if the
  // table first rendered as an empty-state message and the rows arrived later.
  const [element, ref] = useState<HTMLDivElement | null>(null);
  const subscribe = useCallback(
    (notify: () => void) => {
      if (!element || typeof ResizeObserver === "undefined") return () => {};
      const observer = new ResizeObserver(notify);
      observer.observe(element);
      if (element.firstElementChild) observer.observe(element.firstElementChild); // the table itself
      return () => observer.disconnect();
    },
    [element],
  );
  // Read during render, so the right layout is chosen before the first paint: no flash of a table.
  const width = useSyncExternalStore(
    subscribe,
    () => (element ? Math.round(element.getBoundingClientRect().width) : Infinity),
    () => Infinity,
  );
  // A table too wide for its box scrolls inside it. Keyboard users must be able to reach that
  // scroller, so it becomes a focusable, named region, and only while it really scrolls.
  const scrolls = useSyncExternalStore(
    subscribe,
    () => !!element && element.scrollWidth > element.clientWidth + 1,
    () => false,
  );
  return [ref, width < below, scrolls] as const;
}

export type Column<T> = {
  id: string;
  /** Shown as the column heading, and as the label of each value on a phone. */
  header: string;
  cell: (row: T) => ReactNode;
  align?: "right";
  /** The row's title on a phone: shown first, large, without a label. */
  primary?: boolean;
};

/**
 * A real table when there is room. When the table is narrower than `cardsBelow` pixels each row
 * becomes a labelled card, driven by the same columns, so nothing is hidden and nothing scrolls
 * sideways. Give a table with many columns a larger `cardsBelow`.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  loading = false,
  skeletonRows = 6,
  empty,
  cardsBelow = 640,
  totals,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string | number;
  loading?: boolean;
  skeletonRows?: number;
  empty?: ReactNode;
  cardsBelow?: number;
  /** A closing row of totals, by column id. */
  totals?: Record<string, ReactNode>;
}) {
  const [wrap, cards, scrolls] = useCards(cardsBelow);
  if (!loading && rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div
      ref={wrap}
      className={cx(s.wrap, cards && s.cards)}
      {...(scrolls ? { role: "region", tabIndex: 0, "aria-label": caption } : {})}
    >
      <table className={s.table} aria-busy={loading || undefined}>
        <caption className="sr-only">{caption}</caption>
        <thead className={s.head}>
          <tr>
            {columns.map((c) => (
              <th key={c.id} scope="col" className={cx(c.align === "right" && s.right)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: skeletonRows }, (_, i) => (
                <tr key={i} className={s.row} aria-hidden="true">
                  {columns.map((c) => (
                    <td key={c.id} data-label={c.header} data-primary={c.primary || undefined}>
                      <Skeleton width={c.primary ? "60%" : "80%"} />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row, index) => (
                <tr key={rowKey(row, index)} className={s.row}>
                  {columns.map((c) => (
                    <td
                      key={c.id}
                      data-label={c.header}
                      data-primary={c.primary || undefined}
                      className={cx(c.align === "right" && s.right)}
                    >
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
        {totals && !loading && (
          <tfoot>
            <tr className={s.totals}>
              {columns.map((c) => (
                <td
                  key={c.id}
                  data-label={c.header}
                  data-primary={c.primary || undefined}
                  className={cx(c.align === "right" && s.right)}
                >
                  {totals[c.id] ?? ""}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
