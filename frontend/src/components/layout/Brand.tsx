import { Link } from "react-router-dom";
import s from "./Brand.module.css";

/** A plain wordmark: the yellow bar, then the agency and the name of the register. */
export function Brand() {
  return (
    <Link to="/" className={s.brand}>
      <span className={s.mark} aria-hidden="true" />
      <span className={s.text}>
        <span className={s.name}>LASRRA</span>
        <span className={s.sub}>Engineering Audit Register</span>
      </span>
    </Link>
  );
}
