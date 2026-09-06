import { Badge, Paper, Text, Title } from "@mantine/core";
import type { Show } from "../types";
import { OccupancyProgress } from "./OccupancyProgress";
import { ChevronRight } from "./ChevronRight";
import { TeamTag, teamColor } from "./TeamTag";

export function ShowCard({ show, onClick, onAnnouncement, onCopyLink }: { show: Show; onClick: () => void; onAnnouncement?: () => void; onCopyLink?: () => void }) {
  return <Paper className={`show-card${show.isPast ? " is-past" : ""}`} data-team-color={teamColor(show.teamName)}>
    <button type="button" className="show-card-main" onClick={onClick}>
    <div className="card-top">
      <div className="show-card-statuses">
        <Badge color="gray" variant="light">{show.showDateLabel}</Badge>
        {show.isPast && <Badge color="gray" variant="filled">Прошедшее</Badge>}
        {show.hasPublished === false && <Badge color="orange" variant="light">Черновик</Badge>}
      </div>
      <ChevronRight />
    </div>
    <Title order={2}>{show.title}</Title>
    <div className="show-card-tags"><TeamTag name={show.teamName} /><Badge color="gray" variant="outline" radius="sm">{show.city}</Badge></div>
    <Text className="muted">{show.location}</Text>
    <div className="capacity-head"><span>{show.isPast ? "Было записано" : "Заполнено"}</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></div>
    <OccupancyProgress occupied={show.occupiedSeats} capacity={show.maxSeats} />
    </button>
    {!show.isPast && (onAnnouncement || onCopyLink) && <div className="show-card-actions">
      {onCopyLink && <button type="button" onClick={onCopyLink}>Скопировать ссылку</button>}
      {onAnnouncement && <button type="button" onClick={onAnnouncement}>{show.hasPublished ? "Повторить анонс" : "Анонс"}</button>}
    </div>}
  </Paper>;
}
