import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import s from "./Tooltip.module.css";

export const TooltipProvider = RadixTooltip.Provider;

/** A short hint on hover or keyboard focus. Never the only place important information appears. */
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <RadixTooltip.Root delayDuration={300}>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content className={s.content} sideOffset={6}>
          {label}
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
