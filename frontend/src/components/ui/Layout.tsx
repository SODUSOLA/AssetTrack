import { ChevronRight } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import s from "./Layout.module.css";

export type Crumb = { label: string; to?: string };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className={s.crumbs}>
      <ol>
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <Fragment key={`${item.label}-${i}`}>
              <li>
                {item.to && !last ? (
                  <Link to={item.to}>{item.label}</Link>
                ) : (
                  <span aria-current={last ? "page" : undefined}>{item.label}</span>
                )}
              </li>
              {!last && (
                <li aria-hidden="true" className={s.sep}>
                  <ChevronRight size={14} />
                </li>
              )}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}

/** The page title. It receives focus on every navigation so keyboard and screen-reader users land at the top. */
export function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
}) {
  return (
    <header className={s.pageHeader}>
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className={s.titleRow}>
        <div className={s.titles}>
          <h1 id="page-title" tabIndex={-1} className={s.title}>
            {title}
          </h1>
          {subtitle && <p className={s.subtitle}>{subtitle}</p>}
        </div>
        {actions && (
          <div className={s.actions} data-print="hide">
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}

export function DefinitionList({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className={s.dl}>
      {items.map(({ label, value }) => (
        <div key={label} className={s.dlRow}>
          <dt>{label}</dt>
          <dd>{value || <span className={s.none}>Not recorded</span>}</dd>
        </div>
      ))}
    </dl>
  );
}
