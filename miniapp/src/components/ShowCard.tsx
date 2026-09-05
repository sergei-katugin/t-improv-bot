import { Badge, Paper, Progress, Text, Title } from "@mantine/core";
import type { Show } from "../types";

export function ShowCard({ show, onClick }: { show: Show; onClick: () => void }) {
  const fill = Math.min(100, Math.round(show.occupiedSeats / Math.max(1, show.maxSeats) * 100));
  return <Paper component="button" className="show-card" onClick={onClick}>
    <div className="card-top"><Badge color="gray" variant="light">{show.showDateLabel}</Badge><span className="arrow">→</span></div>
    <Title order={2}>{show.title}</Title>
    <Text>{show.teamName}</Text>
    <Text className="muted">{show.location} · {show.city}</Text>
    <div className="capacity-head"><span>Заполнено</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></div>
    <Progress value={fill} color="gray" mt={8} />
  </Paper>;
}
