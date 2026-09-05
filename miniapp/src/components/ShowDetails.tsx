import { Alert, Anchor, Button, Collapse, Progress, Text, Title } from "@mantine/core";
import type { Show } from "../types";
import { BottomActionBar, BottomNavAction } from "./BottomActionBar";

export function ShowDetails({ show, descriptionOpened, onToggleDescription, onAttendees, onEdit, onAnnouncement, onAnalytics, onMore }: {
  show: Show;
  descriptionOpened: boolean;
  onToggleDescription: () => void;
  onAttendees: () => void;
  onEdit: () => void;
  onAnnouncement: () => void;
  onAnalytics: () => void;
  onMore: () => void;
}) {
  const fill = Math.min(100, Math.round(show.occupiedSeats / Math.max(1, show.maxSeats) * 100));
  return <>
    <section className="show-detail">
      <div className="eyebrow">{show.teamName}</div>
      <Title order={1}>{show.title}</Title>
      <Text className="date">{show.showDateLabel}</Text>
      {show.locationUrl ? <Anchor className="place-link" href={show.locationUrl} target="_blank">{show.location} · {show.city} ↗</Anchor> : <Text className="place">{show.location} · {show.city}</Text>}
      <div className="capacity-head"><span>Записи</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></div>
      <Progress value={fill} color="gray" mt={8} />
      {show.registrarUsername && <Anchor className="registrar" href={`https://t.me/${show.registrarUsername}`} target="_blank">Ответственный · @{show.registrarUsername} ↗</Anchor>}
      {show.posterText && <div className="description-block"><Button variant="subtle" size="xs" onClick={onToggleDescription} aria-expanded={descriptionOpened}>{descriptionOpened ? "Скрыть описание" : "Показать описание"}</Button><Collapse expanded={descriptionOpened}><Text className="poster-text">{show.posterText}</Text></Collapse></div>}
    </section>
    {!show.isActive && <Alert color="red" mt="md">Эта афиша отменена. Новые записи недоступны.</Alert>}
    <BottomActionBar navigation>
      <BottomNavAction icon="attendees" label="Зрители" meta={show.occupiedSeats} onClick={onAttendees} />
      <BottomNavAction icon="edit" label="Изменить" onClick={onEdit} />
      <BottomNavAction icon="announce" label="Анонс" onClick={onAnnouncement} />
      <BottomNavAction icon="analytics" label="Аналитика" onClick={onAnalytics} />
      <BottomNavAction icon="more" label="Ещё" onClick={onMore} />
    </BottomActionBar>
  </>;
}
