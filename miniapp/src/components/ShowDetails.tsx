import { Alert, Anchor, Button, Collapse, Text, Title } from "@mantine/core";
import type { Show } from "../types";
import { ShowNavigation } from "./ShowNavigation";
import { OccupancyProgress } from "./OccupancyProgress";
import { ChevronRight } from "./ChevronRight";

export function ShowDetails({ show, descriptionOpened, onToggleDescription, onAttendees, onEdit, onAnnouncement, onAnalytics, onRegistration, onMore }: {
  show: Show;
  descriptionOpened: boolean;
  onToggleDescription: () => void;
  onAttendees: () => void;
  onEdit: () => void;
  onAnnouncement: () => void;
  onAnalytics: () => void;
  onRegistration: () => void;
  onMore: () => void;
}) {
  return <>
    <section className="show-detail">
      <div className="page-heading show-heading">
        <Title order={1}>{show.title}</Title>
        <Text className="show-team">{show.teamName}</Text>
      </div>
      <Text className="date">{show.showDateLabel}</Text>
      {show.locationUrl ? <Anchor className="place-link" href={show.locationUrl} target="_blank">{show.location} · {show.city} ↗</Anchor> : <Text className="place">{show.location} · {show.city}</Text>}
      <button type="button" className="show-attendance-summary" onClick={onAttendees}>
        <span className="capacity-head"><span>Записи</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></span>
        <OccupancyProgress occupied={show.occupiedSeats} capacity={show.maxSeats} />
        <span className="show-attendance-link">Открыть список зрителей <ChevronRight /></span>
      </button>
      <div className="show-status-row"><span>Статус</span><strong>{show.isPast ? "Шоу завершилось" : !show.isActive ? "Афиша отменена" : show.registrationClosed ? "Запись закрыта автоматически" : "Запись открыта"}</strong></div>
      {!show.isPast && show.isActive && !show.registrationClosesAt && <Alert color="yellow" mt="md">Автозакрытие не настроено — запись будет доступна до начала шоу.</Alert>}
      {show.registrarUsername && <Anchor className="registrar" href={`https://t.me/${show.registrarUsername}`} target="_blank">Ответственный · @{show.registrarUsername} ↗</Anchor>}
      {show.posterText && <div className="description-block"><Button variant="subtle" size="xs" onClick={onToggleDescription} aria-expanded={descriptionOpened}>{descriptionOpened ? "Скрыть описание" : "Показать описание"}</Button><Collapse expanded={descriptionOpened}><Text className="poster-text">{show.posterText}</Text></Collapse></div>}
    </section>
    {show.isPast ? <Alert color="gray" mt="md">Шоу завершилось. Доступны список зрителей и итоговая аналитика.</Alert> : !show.isActive && <Alert color="red" mt="md">Эта афиша отменена. Новые записи недоступны.</Alert>}
    <ShowNavigation show={show} active="show" onShow={() => undefined} onEdit={onEdit} onAnnouncement={onAnnouncement} onAnalytics={onAnalytics} onRegistration={onRegistration} onMore={onMore} />
  </>;
}
