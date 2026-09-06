import React from "react";
import { Alert, Anchor, Autocomplete, Badge, Button, Collapse, FileInput, Group, Loader, Modal, NumberInput, Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text, Textarea, TextInput, Title } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { BottomActionBar, RootNavigation } from "../components/BottomActionBar";
import { ShowNavigation } from "../components/ShowNavigation";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { ShowStepper } from "../components/ShowStepper";
import { api, authenticatedBlob } from "../lib/api";
import { telegramConfirm, telegramHaptic } from "../lib/telegram";
import { useAppResume } from "../hooks/useAppResume";
import type { AccessUser, Attendees, AuditItem, Me, Options, Promotion, RegistrationChatOption, Show, ShowFormValue, ThemePreference } from "../types";
import { previewAttendees } from "./ManagementModal";
import { OccupancyProgress } from "../components/OccupancyProgress";
import { AttendeeStatus } from "../components/AttendeeStatus";

export function AttendeesModal({ opened, onClose, show, demo, backHandlerRef, onEdit, onAnnouncement, onAnalytics, onRegistration, onMore }: {
  opened: boolean; onClose: () => void; show: Show; demo: boolean;
  backHandlerRef: React.MutableRefObject<(() => boolean) | null>;
  onEdit: () => void; onAnnouncement: () => void; onAnalytics: () => void; onRegistration: () => void; onMore: () => void;
}) {
  const [data, setData] = React.useState<Attendees | null>(demo ? previewAttendees : null);
  const [loading, setLoading] = React.useState(!demo);
  const [search, setSearch] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState<{ kind: "registration" | "manual"; id: number; name: string } | null>(null);
  const [listOpened, setListOpened] = React.useState(false);

  const load = React.useCallback(async (offset = 0, append = false) => {
    if (demo) { setData(previewAttendees); return; }
    setLoading(true);
    try {
      const query = new URLSearchParams({ offset: String(offset) });
      if (search.trim()) query.set("search", search.trim());
      const next = await api<Attendees>(`/api/miniapp/shows/${show.id}/attendees?${query}`);
      setData((current) => append && current ? {
        ...next,
        registrations: [...current.registrations, ...next.registrations],
        manual: [...current.manual, ...next.manual],
      } : next);
    }
    catch (reason) { notifications.show({ color: "red", title: "Не удалось загрузить записи", message: (reason as Error).message }); }
    finally { setLoading(false); }
  }, [demo, search, show.id]);

  React.useEffect(() => { if (opened) void load(); }, [opened, load]);
  React.useEffect(() => {
    if (!opened) { setListOpened(false); backHandlerRef.current = null; return; }
    backHandlerRef.current = () => {
      if (!listOpened) return false;
      setListOpened(false); setSearch(""); return true;
    };
    return () => { backHandlerRef.current = null; };
  }, [backHandlerRef, listOpened, opened]);
  useAppResume(() => { void load(0); }, opened);

  async function mutate(key: string, path: string, method: string, body?: object) {
    setBusy(key);
    try {
      await api(path, { method, body: body ? JSON.stringify(body) : undefined });
      if (!demo) await load(0);
      notifications.show({ color: "gray", title: "Список обновлён", message: "Изменения сохранены" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось изменить запись", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function removeConfirmed() {
    if (!confirmDelete) return;
    const item = confirmDelete;
    setConfirmDelete(null);
    if (item.kind === "registration") {
      await mutate(`cancel-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "DELETE");
    } else {
      await mutate(`delete-${item.id}`, `/api/miniapp/shows/${show.id}/manual-attendees/${item.id}`, "DELETE");
    }
  }

  return <Modal opened={opened} onClose={onClose} title={listOpened ? "Список зрителей" : `Записи · ${show.title}`} fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    {loading && <Stack><Skeleton height={100} /><Skeleton height={100} /></Stack>}
    {data && !listOpened && <Stack gap="md">
      <Paper className="attendance-summary"><Group justify="space-between"><div><Text size="sm" c="dimmed">Записано</Text><Title order={2}>{data.occupied} / {data.maxSeats}</Title></div><div><Text size="sm" c="dimmed">Пришли</Text><Title order={2}>{data.arrived}</Title></div></Group><OccupancyProgress occupied={data.occupied} capacity={data.maxSeats} mt="md" /></Paper>
      <Button variant="default" fullWidth onClick={() => setListOpened(true)}>Список зрителей · {data.registrations.length + data.manual.length}</Button>
    </Stack>}
    {data && listOpened && <Stack gap="md">
      <TextInput aria-label="Фильтр зрителей" placeholder="Имя или @username" value={search} onChange={(event) => setSearch(event.currentTarget.value)} autoFocus />
      <Title order={3}>Записались через бот</Title>
      {data.registrations.map((item) => <Paper className="attendee-card" key={item.id}><Stack gap="sm"><Group justify="space-between" align="flex-start"><div><Text fw={750}>{item.name}{item.guests ? ` +${item.guests}` : ""}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}<AttendeeStatus confirmed={item.confirmed} checkedInCount={item.checkedInCount} /></div><Badge color={item.checkedInCount ? "green" : "gray"}>{item.checkedInCount} / {item.guests + 1}</Badge></Group><Group justify="space-between"><Group gap="xs"><Button size="xs" variant="light" disabled={item.checkedInCount <= 0 || busy !== null} onClick={() => mutate(`check-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount - 1 })}>− Пришли</Button><Button size="xs" variant="light" disabled={item.checkedInCount >= item.guests + 1 || busy !== null} onClick={() => mutate(`check-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount + 1 })}>+ Пришли</Button></Group><Button size="xs" color="red" variant="subtle" loading={busy === `cancel-${item.id}`} onClick={() => setConfirmDelete({ kind: "registration", id: item.id, name: item.name })}>Отменить</Button></Group></Stack></Paper>)}
      <Title order={3}>Добавлены вручную</Title>
      {data.manual.map((item) => <Paper className="attendee-card" key={item.id}><Stack gap="sm"><Group justify="space-between" align="flex-start"><div><Text fw={750}>{item.name}{item.guests ? ` +${item.guests}` : ""}</Text>{item.contact && <Text size="sm" c="dimmed">{item.contact}</Text>}<AttendeeStatus checkedInCount={item.checkedInCount} manual /></div><Badge color={item.checkedInCount ? "green" : "gray"}>{item.checkedInCount} / {item.guests + 1}</Badge></Group><Group justify="space-between"><Group gap="xs"><Button size="xs" variant="light" disabled={item.checkedInCount <= 0 || busy !== null} onClick={() => mutate(`manual-${item.id}`, `/api/miniapp/shows/${show.id}/manual-attendees/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount - 1 })}>− Пришли</Button><Button size="xs" variant="light" disabled={item.checkedInCount >= item.guests + 1 || busy !== null} onClick={() => mutate(`manual-${item.id}`, `/api/miniapp/shows/${show.id}/manual-attendees/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount + 1 })}>+ Пришли</Button></Group><Button size="xs" color="red" variant="subtle" loading={busy === `delete-${item.id}`} onClick={() => setConfirmDelete({ kind: "manual", id: item.id, name: item.name })}>Удалить</Button></Group></Stack></Paper>)}
      {data.waitlist.length > 0 && <><Title order={3}>Лист ожидания · {data.waitlist.length}</Title>{data.waitlist.map((item) => <Paper className="attendee-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.name}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}</div><Badge color="yellow">№ {item.position}</Badge></Group></Paper>)}</>}
      {data.hasMore && <Button variant="default" loading={loading} onClick={() => void load(data.nextOffset, true)}>Показать ещё</Button>}
    </Stack>}
    {data && <ShowNavigation show={show} onShow={onClose} onEdit={onEdit} onAnnouncement={onAnnouncement} onAnalytics={onAnalytics} onRegistration={onRegistration} onMore={onMore} />}
    <Modal opened={confirmDelete !== null} onClose={() => setConfirmDelete(null)} title="Подтвердить действие" centered>
      <Text>Удалить запись «{confirmDelete?.name}»? Это освободит место в афише.</Text>
      <Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setConfirmDelete(null)}>Не удалять</Button><Button color="red" onClick={removeConfirmed}>Удалить</Button></Group>
    </Modal>
  </Modal>;
}
