import { Badge, Paper, Text, Title } from "@mantine/core";
import type { Show } from "../types";
import { OccupancyProgress } from "./OccupancyProgress";
import { ChevronRight } from "./ChevronRight";
import { TeamTag, teamColor } from "./TeamTag";

export function ShowCard({ show, onClick }: { show: Show; onClick: () => void }) {
  return <Paper component="button" className={`show-card${show.isPast ? " is-past" : ""}`} data-team-color={teamColor(show.teamName)} onClick={onClick}>
    <div className="card-top">
      <div className="show-card-statuses">
        <Badge color="gray" variant="light">{show.showDateLabel}</Badge>
        {!show.hasPublished && <Badge color="orange" variant="light">Черновик</Badge>}
      </div>
      <ChevronRight />
    </div>
    <Title order={2}>{show.title}</Title>
    <div className="show-card-tags"><TeamTag name={show.teamName} /><Badge color="gray" variant="outline" radius="sm">{show.city}</Badge></div>
    <Text className="muted">{show.location}</Text>
    <div className="capacity-head"><span>{show.isPast ? "Было записано" : "Заполнено"}</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></div>
    <OccupancyProgress occupied={show.occupiedSeats} capacity={show.maxSeats} />
  </Paper>;
}
