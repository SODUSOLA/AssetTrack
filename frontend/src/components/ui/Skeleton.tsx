import type { CSSProperties } from "react";
import s from "./Skeleton.module.css";

/** A placeholder block shaped like the content that is loading. Hidden from screen readers. */
export function Skeleton({ width, height }: { width?: string; height?: string }) {
  const style: CSSProperties = { width, height };
  return <span aria-hidden="true" className={s.skeleton} style={style} />;
}
