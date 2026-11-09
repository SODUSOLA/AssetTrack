import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./Button";
import s from "./Pagination.module.css";

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  noun = "results",
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  noun?: string;
}) {
  if (total === 0) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const pages = Math.ceil(total / pageSize);
  return (
    <nav aria-label="Pagination" className={s.pagination}>
      <p className={s.summary} aria-live="polite">
        Showing {first}–{last} of {total} {noun}
      </p>
      {pages > 1 && (
        <div className={s.buttons}>
          <Button
            size="sm"
            icon={<ChevronLeft size={16} aria-hidden="true" />}
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </Button>
          <span className={s.position}>
            Page {page} of {pages}
          </span>
          <Button size="sm" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
            Next
            <ChevronRight size={16} aria-hidden="true" />
          </Button>
        </div>
      )}
    </nav>
  );
}
