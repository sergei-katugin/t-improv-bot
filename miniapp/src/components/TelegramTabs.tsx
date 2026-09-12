import { FloatingIndicator, Tabs } from "@mantine/core";
import { useRef, useState } from "react";
import "./TelegramTabs.css";

export function TelegramTabs<T extends string>({ value, onChange, items, label }: {
  value: T;
  onChange: (value: T) => void;
  items: readonly { value: T; label: string }[];
  label: string;
}) {
  const [parent, setParent] = useState<HTMLDivElement | null>(null);
  const [controls, setControls] = useState<Record<string, HTMLButtonElement | null>>({});
  const callbacks = useRef<Record<string, (node: HTMLButtonElement | null) => void>>({});
  function controlRef(key: string) {
    callbacks.current[key] ??= (node) => setControls((previous) =>
      previous[key] === node ? previous : { ...previous, [key]: node });
    return callbacks.current[key];
  }
  return <Tabs value={value} onChange={(next) => { if (next) onChange(next as T); }} className="telegram-tabs">
    <Tabs.List ref={setParent} aria-label={label}>
      <FloatingIndicator target={controls[value]} parent={parent} className="telegram-tabs-indicator" transitionDuration={220} />
      {items.map((item) => <Tabs.Tab key={item.value} value={item.value}
        ref={controlRef(item.value)}>
        {item.label}
      </Tabs.Tab>)}
    </Tabs.List>
  </Tabs>;
}
