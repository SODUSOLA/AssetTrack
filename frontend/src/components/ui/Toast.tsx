import { X } from "lucide-react";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import { IconButton } from "./Button";
import s from "./Toast.module.css";

type ToastItem = { id: number; title: string; description?: string; tone: ToastTone };

import { ToastContext, type ToastApi, type ToastTone } from "./toastContext";

/** Confirmations and non-blocking errors. The region is announced by screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const show = useCallback<ToastApi["show"]>(
    ({ title, description, tone = "success" }) => {
      const id = nextId.current++;
      setItems((current) => [...current.slice(-3), { id, title, description, tone }]);
      // Errors stay longer: they usually need to be read twice.
      window.setTimeout(() => dismiss(id), tone === "error" ? 12_000 : 6_000);
    },
    [dismiss],
  );

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className={s.region} role="region" aria-label="Notifications" aria-live="polite">
        {items.map((item) => (
          <div
            key={item.id}
            role={item.tone === "error" ? "alert" : "status"}
            className={cx(s.toast, s[item.tone])}
          >
            <div className={s.text}>
              <p className={s.title}>{item.title}</p>
              {item.description && <p>{item.description}</p>}
            </div>
            <IconButton
              label="Dismiss notification"
              icon={<X size={16} aria-hidden="true" />}
              onClick={() => dismiss(item.id)}
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
