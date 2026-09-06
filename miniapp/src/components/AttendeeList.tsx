import { Anchor, Text } from "@mantine/core";

export function AttendeeList({ items }: { items: Array<{ id: number; name: string; username?: string | null; contact?: string | null; guests?: number }> }) {
  return <div className="attendee-list">{items.map((item) => <div className="attendee-list-row" key={item.id}>
    <div><Text fw={700}>{item.name}</Text>{item.username ? <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor> : item.contact && <Text size="sm" c="dimmed">{item.contact}</Text>}</div>
    <Text size="sm" c="dimmed">{(item.guests ?? 0) + 1} {(item.guests ?? 0) === 0 ? "место" : "места"}</Text>
  </div>)}</div>;
}
