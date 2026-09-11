import { Autocomplete, Button, Group, Modal, NumberInput, Paper, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { BottomActionBar } from "../components/BottomActionBar";
import type { Options } from "../types";

const sheetProps = {
  size: 620,
  xOffset: 0,
  yOffset: 0,
  transitionProps: { transition: "slide-up" as const, duration: 240, timingFunction: "ease-out" },
};

export function TeamsSheet({ opened, editorOpened, id, name, members, invalidMember, saving, teams, onClose, onName, onMembers, onEdit, onDelete, onAdd, onSave }: {
  opened: boolean; editorOpened: boolean; id: number | null; name: string; members: string; invalidMember: string | null;
  saving: boolean; teams: Options["teams"]; onClose: () => void; onName: (value: string) => void; onMembers: (value: string) => void;
  onEdit: (team: Options["teams"][number]) => void; onDelete: (team: Options["teams"][number]) => void; onAdd: () => void; onSave: () => void;
}) {
  return <Modal {...sheetProps} opened={opened} onClose={onClose} title={editorOpened ? (id ? "Редактировать команду" : "Новая команда") : "Команды"} closeButtonProps={{ "aria-label": editorOpened ? "Закрыть редактор команды" : "Закрыть команды" }} classNames={{ inner: "show-form-sheet-inner", content: "teams-sheet", close: "show-form-close" }}>
    {editorOpened ? <Stack gap="lg">
      <TextInput label="Название" value={name} onChange={(event) => onName(event.currentTarget.value)} autoFocus />
      <Textarea label="Telegram-ники участников" description="Через запятую или с новой строки. Ник содержит 5–32 латинских символа, цифры или _." placeholder="@sergey, @anna_impro" value={members} error={invalidMember ? `Проверь ник: ${invalidMember}` : undefined} onChange={(event) => onMembers(event.currentTarget.value)} autosize minRows={4} />
      <BottomActionBar inline><Button className="primary" fullWidth disabled={!name.trim() || Boolean(invalidMember)} loading={saving} onClick={onSave}>{id ? "Сохранить" : "Добавить команду"}</Button></BottomActionBar>
    </Stack> : <Stack>
      {teams.map((team) => <Paper className="resource-card" key={team.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{team.name}</Text><Text size="sm" c="dimmed">{team.members || "Участники не указаны"}</Text></div><Group gap="xs"><Button size="xs" variant="light" onClick={() => onEdit(team)}>Изменить</Button><Button size="xs" color="red" variant="subtle" onClick={() => onDelete(team)}>Удалить</Button></Group></Group></Paper>)}
      {!teams.length && <Text c="dimmed">Команд пока нет.</Text>}
      <BottomActionBar inline><Button className="primary" fullWidth onClick={onAdd}>＋ Добавить команду</Button></BottomActionBar>
    </Stack>}
  </Modal>;
}

export function VenuesSheet({ opened, editorOpened, id, name, city, url, seats, saving, venues, onClose, onName, onCity, onUrl, onSeats, onEdit, onDelete, onAdd, onSave }: {
  opened: boolean; editorOpened: boolean; id: number | null; name: string; city: string; url: string; seats: number; saving: boolean;
  venues: Options["venues"]; onClose: () => void; onName: (value: string) => void; onCity: (value: string) => void; onUrl: (value: string) => void;
  onSeats: (value: number) => void; onEdit: (venue: Options["venues"][number]) => void; onDelete: (venue: Options["venues"][number]) => void; onAdd: () => void; onSave: () => void;
}) {
  return <Modal {...sheetProps} opened={opened} onClose={onClose} title={editorOpened ? (id ? "Редактировать площадку" : "Новая площадка") : "Площадки"} closeButtonProps={{ "aria-label": editorOpened ? "Закрыть редактор площадки" : "Закрыть площадки" }} classNames={{ inner: "show-form-sheet-inner", content: "venues-sheet", close: "show-form-close" }}>
    {editorOpened ? <Stack gap="lg">
      <TextInput label="Название" value={name} onChange={(event) => onName(event.currentTarget.value)} autoFocus />
      <Autocomplete label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={city} onChange={onCity} />
      <NumberInput min={1} label="Количество мест" value={seats} onChange={(value) => onSeats(typeof value === "number" ? value : 1)} />
      <TextInput type="url" label="Ссылка на карту" description="Необязательно" placeholder="https://maps.google.com/…" value={url} onChange={(event) => onUrl(event.currentTarget.value)} />
      <BottomActionBar inline><Button className="primary" fullWidth disabled={!name.trim() || !city.trim()} loading={saving} onClick={onSave}>{id ? "Сохранить" : "Добавить площадку"}</Button></BottomActionBar>
    </Stack> : <Stack>
      {venues.map((venue) => <Paper className="resource-card" key={venue.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{venue.name}</Text><Text size="sm" c="dimmed">{venue.city} · {venue.defaultSeats} мест</Text></div><Group gap="xs"><Button size="xs" variant="light" onClick={() => onEdit(venue)}>Изменить</Button><Button size="xs" color="red" variant="subtle" onClick={() => onDelete(venue)}>Удалить</Button></Group></Group></Paper>)}
      {!venues.length && <Text c="dimmed">Площадок пока нет.</Text>}
      <BottomActionBar inline><Button className="primary" fullWidth onClick={onAdd}>＋ Добавить площадку</Button></BottomActionBar>
    </Stack>}
  </Modal>;
}
