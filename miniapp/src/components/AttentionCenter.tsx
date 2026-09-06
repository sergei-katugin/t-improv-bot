import { Badge, Paper, Stack, Text, Title } from "@mantine/core";
import { ChevronRight } from "./ChevronRight";

export type AttentionItem = { showId: number; showTitle: string; kind: "announcement" | "chat" | "edit"; label: string };

export function AttentionCenter({ items, onOpen }: { items: AttentionItem[]; onOpen: (item: AttentionItem) => void }) {
  if (!items.length) return null;
  return <Paper className="attention-center"><div className="attention-center-heading"><Title order={3}>Требует внимания</Title><Badge color="orange" variant="light">{items.length}</Badge></div><Stack gap={0}>{items.map((item, index) => <button type="button" key={`${item.showId}-${item.kind}-${index}`} onClick={() => onOpen(item)}><span><b>{item.label}</b><small>{item.showTitle}</small></span><ChevronRight /></button>)}</Stack></Paper>;
}
