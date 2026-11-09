import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import s from "./Tabs.module.css";

export type TabItem = { value: string; label: string; content: ReactNode };

/** Keyboard-navigable tabs (arrow keys, Home, End) with the right roles from Radix. */
export function Tabs({
  items,
  value,
  onValueChange,
  label,
}: {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  label: string;
}) {
  return (
    <RadixTabs.Root value={value} onValueChange={onValueChange}>
      <RadixTabs.List aria-label={label} className={s.list}>
        {items.map((item) => (
          <RadixTabs.Trigger key={item.value} value={item.value} className={s.trigger}>
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value} className={s.content}>
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
