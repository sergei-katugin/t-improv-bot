import React from "react";
import ReactDOM from "react-dom/client";
import {
  Alert, Anchor, Badge, Button, FileInput, Group, Loader, MantineProvider, Modal, NumberInput,
  Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text,
  Textarea, TextInput, Title, createTheme,
} from "@mantine/core";
import { Notifications, notifications } from "@mantine/notifications";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles.css";

type Show = {
  id: number;
  title: string;
  teamName: string;
  showDateLabel: string;
  showDateLocal?: string;
  location: string;
  locationUrl?: string | null;
  city: string;
  isActive: boolean;
  maxSeats: number;
  occupiedSeats: number;
  registrarUsername: string | null;
  registrationUrl?: string;
  posterText?: string | null;
  feedbackEnabled?: boolean;
  checkinEnabled?: boolean;
  hasPoster?: boolean;
};

type Options = {
  teams: { id: number; name: string; members: string | null }[];
  venues: { id: number; name: string; city: string; mapsUrl: string | null; defaultSeats: number }[];
  adChannels: { id: number; username: string; isActive: boolean }[];
};

type Me = { id: number; firstName: string | null; username: string | null; role: "organizer" | "admin" };
type AccessUser = { id: number; telegramId: number; username: string | null; firstName: string | null; lastName: string | null; role: "organizer" | "admin"; isCurrent: boolean; isProtected: boolean };
type AuditItem = { id: number; action: string; entityType: string; entityId: number | null; details: Record<string, unknown> | null; createdAt: string; actor: { id: number; username: string | null; firstName: string | null; lastName: string | null; telegramId: number } | null };

type Attendees = {
  occupied: number; maxSeats: number; arrived: number; hasMore: boolean; nextOffset: number;
  registrations: { id: number; name: string; guests: number; username: string | null; confirmed: boolean | null; checkedInCount: number; source: string | null }[];
  manual: { id: number; name: string; contact: string | null; checkedInCount: number; source: string | null }[];
};

type Promotion = {
  html: string; text: string; registrationUrl: string; hasPoster: boolean; hasPublished: boolean;
  channels: { id: number; username: string; url: string }[];
};

type Analytics = {
  registered: number; capacity: number; cancelledRegistrations: number; confirmed: number;
  arrived: number; checkinEnabled: boolean; feedbackEnabled: boolean; feedbackCount: number;
  averageRating: number; ratingDistribution: Record<string, number>;
  sources: { source: string; count: number }[];
  comments: { id: number; rating: number; comment: string; username: string | null; name: string | number; createdAt: string }[];
  commentsLimit: number;
};

type ShowFormValue = {
  title: string; teamName: string; showDateLocal: string; location: string;
  locationUrl: string; city: string; posterText: string; maxSeats: number;
  registrarUsername: string; checkinEnabled: boolean; feedbackEnabled: boolean;
};

const previewShows: Show[] = [
  { id: 1, title: "Истории на ночь", teamName: "T·IMPRO", showDateLabel: "5 сентября, 20:00", location: "Ravens Music Hall", city: "Лимасол", isActive: true, maxSeats: 50, occupiedSeats: 34, registrarUsername: "sergey" },
  { id: 2, title: "Маэстро", teamName: "Импровизаторы Кипра", showDateLabel: "12 сентября, 19:30", location: "Yurts in Cyprus", city: "Пафос", isActive: true, maxSeats: 40, occupiedSeats: 18, registrarUsername: "anna_impro" },
];

const theme = createTheme({
  primaryColor: "violet",
  defaultRadius: "md",
  fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  headings: { fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
});

function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const demoMutation = import.meta.env.DEV &&
    new URLSearchParams(location.search).get("preview") === "1" &&
    init.method && init.method !== "GET";
  if (demoMutation) return Promise.resolve({ id: Date.now(), isActive: true } as T);
  const initData = window.Telegram?.WebApp.initData ?? "";
  const isForm = init.body instanceof FormData;
  return fetch(path, {
    ...init,
    headers: { ...(!isForm && { "Content-Type": "application/json" }), Authorization: `tma ${initData}`, ...init.headers },
  }).then(async (response) => {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const message = response.status === 401 ? "Открой Mini App из админ-бота" :
        payload.field ? `Проверь поле: ${payload.field}` : "Не удалось сохранить данные";
      throw new Error(message);
    }
    return response.json() as Promise<T>;
  });
}

async function authenticatedBlob(path: string): Promise<Blob> {
  const initData = window.Telegram?.WebApp.initData ?? "";
  const response = await fetch(path, { headers: { Authorization: `tma ${initData}` } });
  if (!response.ok) throw new Error("Не удалось загрузить изображение");
  return response.blob();
}

function emptyForm(): ShowFormValue {
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  return { title: "", teamName: "", showDateLocal: local, location: "", locationUrl: "", city: "Лимасол", posterText: "", maxSeats: 50, registrarUsername: "", checkinEnabled: false, feedbackEnabled: false };
}

function formFromShow(show: Show): ShowFormValue {
  return {
    title: show.title, teamName: show.teamName, showDateLocal: show.showDateLocal ?? "",
    location: show.location, locationUrl: show.locationUrl ?? "", city: show.city,
    posterText: show.posterText ?? "", maxSeats: show.maxSeats,
    registrarUsername: show.registrarUsername ? `@${show.registrarUsername}` : "",
    checkinEnabled: show.checkinEnabled ?? false, feedbackEnabled: show.feedbackEnabled ?? false,
  };
}

function ShowForm({ opened, initial, options, onClose, onSaved }: {
  opened: boolean; initial: Show | null; options: Options; onClose: () => void; onSaved: (id: number) => void;
}) {
  const [value, setValue] = React.useState<ShowFormValue>(emptyForm());
  const [venueId, setVenueId] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => { if (opened) { setValue(initial ? formFromShow(initial) : emptyForm()); setVenueId(null); } }, [opened, initial]);
  const set = <K extends keyof ShowFormValue>(key: K, next: ShowFormValue[K]) => setValue((current) => ({ ...current, [key]: next }));

  function selectVenue(id: string | null) {
    setVenueId(id);
    const venue = options.venues.find((item) => String(item.id) === id);
    if (venue) setValue((current) => ({ ...current, location: venue.name, city: venue.city, locationUrl: venue.mapsUrl ?? "", maxSeats: venue.defaultSeats }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const result = await api<{ id: number }>(initial ? `/api/miniapp/shows/${initial.id}` : "/api/miniapp/shows", {
        method: initial ? "PATCH" : "POST", body: JSON.stringify(value),
      });
      notifications.show({ color: "violet", title: initial ? "Афиша обновлена" : "Афиша создана", message: "Изменения сохранены" });
      onSaved(result.id);
    } catch (reason) {
      notifications.show({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message });
    } finally { setSaving(false); }
  }

  return <Modal opened={opened} onClose={onClose} title={initial ? "Редактировать афишу" : "Новая афиша"} fullScreen>
    <form onSubmit={submit} className="show-form">
      <Stack gap="md">
        <TextInput required label="Название" value={value.title} onChange={(e) => set("title", e.currentTarget.value)} maxLength={256} />
        <Select required searchable allowDeselect={false} label="Команда" data={options.teams.map((team) => ({ value: team.name, label: team.name }))} value={value.teamName || null} onChange={(next) => set("teamName", next ?? "")} />
        <TextInput required type="datetime-local" label="Дата и время" value={value.showDateLocal} onChange={(e) => set("showDateLocal", e.currentTarget.value)} />
        <Select searchable clearable label="Выбрать площадку" placeholder="Или заполнить вручную" data={options.venues.map((venue) => ({ value: String(venue.id), label: `${venue.name} · ${venue.city}` }))} value={venueId} onChange={selectVenue} />
        <TextInput required label="Площадка" value={value.location} onChange={(e) => set("location", e.currentTarget.value)} maxLength={512} />
        <SimpleGrid cols={2}><TextInput required label="Город" value={value.city} onChange={(e) => set("city", e.currentTarget.value)} /><NumberInput required min={1} max={10000} label="Количество мест" value={value.maxSeats} onChange={(next) => set("maxSeats", typeof next === "number" ? next : 1)} /></SimpleGrid>
        <TextInput type="url" label="Ссылка на карту" value={value.locationUrl} onChange={(e) => set("locationUrl", e.currentTarget.value)} />
        <TextInput label="Ответственный в Telegram" placeholder="@username" value={value.registrarUsername} onChange={(e) => set("registrarUsername", e.currentTarget.value)} />
        <Textarea label="Текст афиши" autosize minRows={5} maxLength={1800} value={value.posterText} onChange={(e) => set("posterText", e.currentTarget.value)} />
        <Switch label="Включить check-in" checked={value.checkinEnabled} onChange={(e) => set("checkinEnabled", e.currentTarget.checked)} />
        <Switch label="Запрашивать отзывы после шоу" checked={value.feedbackEnabled} onChange={(e) => set("feedbackEnabled", e.currentTarget.checked)} />
        <Button type="submit" loading={saving} size="md">{initial ? "Сохранить изменения" : "Создать афишу"}</Button>
      </Stack>
    </form>
  </Modal>;
}

function ManagementModal({ opened, onClose, me, options, reload }: {
  opened: boolean; onClose: () => void; me: Me | null; options: Options; reload: () => Promise<void>;
}) {
  const [teamId, setTeamId] = React.useState<number | null>(null);
  const [teamName, setTeamName] = React.useState("");
  const [members, setMembers] = React.useState("");
  const [venueName, setVenueName] = React.useState("");
  const [venueCity, setVenueCity] = React.useState("Лимасол");
  const [venueUrl, setVenueUrl] = React.useState("");
  const [venueSeats, setVenueSeats] = React.useState(50);
  const [channel, setChannel] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [accessUsers, setAccessUsers] = React.useState<AccessUser[]>([]);
  const [accessLoading, setAccessLoading] = React.useState(false);
  const [inviteUrl, setInviteUrl] = React.useState<string | null>(null);
  const [revokeUser, setRevokeUser] = React.useState<AccessUser | null>(null);
  const [auditItems, setAuditItems] = React.useState<AuditItem[]>([]);
  const [auditLoading, setAuditLoading] = React.useState(false);

  const loadAccess = React.useCallback(async () => {
    if (me?.role !== "admin") return;
    setAccessLoading(true);
    try {
      if (import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1") {
        setAccessUsers([{ id: 1, telegramId: 416607535, username: "sergey", firstName: "Sergey", lastName: null, role: "admin", isCurrent: true, isProtected: true }, { id: 2, telegramId: 123, username: "anna_impro", firstName: "Анна", lastName: null, role: "organizer", isCurrent: false, isProtected: false }]);
      } else setAccessUsers((await api<{ items: AccessUser[] }>("/api/miniapp/access/users")).items);
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось загрузить доступы", message: (reason as Error).message }); }
    finally { setAccessLoading(false); }
  }, [me?.role]);

  React.useEffect(() => { if (opened) void loadAccess(); }, [opened, loadAccess]);

  const loadAudit = React.useCallback(async () => {
    if (me?.role !== "admin") return;
    setAuditLoading(true);
    try {
      const preview = import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1";
      if (preview) setAuditItems([
        { id: 1, action: "show.published", entityType: "show", entityId: 1, details: { messageId: 123 }, createdAt: new Date().toISOString(), actor: { id: 1, username: "sergey", firstName: "Sergey", lastName: null, telegramId: 416607535 } },
        { id: 2, action: "access.invite_created", entityType: "invite", entityId: 5, details: { role: "organizer" }, createdAt: new Date(Date.now() - 3600000).toISOString(), actor: { id: 1, username: "sergey", firstName: "Sergey", lastName: null, telegramId: 416607535 } },
      ]); else setAuditItems((await api<{ items: AuditItem[] }>("/api/miniapp/audit-log")).items);
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось загрузить журнал", message: (reason as Error).message }); }
    finally { setAuditLoading(false); }
  }, [me?.role]);

  React.useEffect(() => { if (opened) void loadAudit(); }, [opened, loadAudit]);

  async function perform(action: () => Promise<unknown>, success: string) {
    setSaving(true);
    try {
      await action(); await reload();
      notifications.show({ color: "violet", title: success, message: "Справочник обновлён" });
    } catch (reason) {
      notifications.show({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message });
    } finally { setSaving(false); }
  }

  function editTeam(team: Options["teams"][number]) {
    setTeamId(team.id); setTeamName(team.name); setMembers(team.members ?? "");
  }

  async function createInvite() {
    setSaving(true);
    try {
      const preview = import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1";
      const result = preview ? { url: "https://t.me/ImprovCypEventBot?start=inv_demo", ttlHours: 24 } : await api<{ url: string; ttlHours: number }>("/api/miniapp/access/invites", { method: "POST", body: JSON.stringify({ role: "organizer" }) });
      setInviteUrl(result.url);
      notifications.show({ color: "green", title: "Ссылка создана", message: `Одноразовая, действует ${result.ttlHours} ч.` });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось создать приглашение", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  async function copyInvite() {
    if (!inviteUrl) return;
    try { await navigator.clipboard.writeText(inviteUrl); notifications.show({ color: "green", title: "Скопировано", message: "Отправьте ссылку будущему организатору" }); }
    catch { notifications.show({ color: "red", title: "Не удалось скопировать", message: inviteUrl }); }
  }

  async function confirmRevoke() {
    if (!revokeUser) return;
    setSaving(true);
    try {
      await api(`/api/miniapp/access/users/${revokeUser.id}`, { method: "PATCH", body: JSON.stringify({ role: "user" }) });
      setRevokeUser(null); await loadAccess();
      notifications.show({ color: "green", title: "Доступ отозван", message: "Пользователь больше не может управлять афишами" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось изменить доступ", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  return <Modal opened={opened} onClose={onClose} title="Настройки и справочники" fullScreen>
    <Tabs defaultValue="teams">
      <Tabs.List grow><Tabs.Tab value="teams">Команды</Tabs.Tab>{me?.role === "admin" && <Tabs.Tab value="venues">Площадки</Tabs.Tab>}{me?.role === "admin" && <Tabs.Tab value="channels">Каналы</Tabs.Tab>}{me?.role === "admin" && <Tabs.Tab value="access">Доступ</Tabs.Tab>}{me?.role === "admin" && <Tabs.Tab value="audit">Журнал</Tabs.Tab>}</Tabs.List>
      <Tabs.Panel value="teams" pt="lg"><Stack>
        {options.teams.map((team) => <Paper className="resource-card" key={team.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{team.name}</Text><Text size="sm" c="dimmed">{team.members || "Участники не указаны"}</Text></div><Button size="xs" variant="light" onClick={() => editTeam(team)}>Изменить</Button></Group></Paper>)}
        <Paper className="resource-form"><Stack>
          <Title order={3}>{teamId ? "Редактировать команду" : "Новая команда"}</Title>
          <TextInput label="Название" value={teamName} onChange={(e) => setTeamName(e.currentTarget.value)} />
          <Textarea label="Telegram-ники участников" description="Через запятую или с новой строки" placeholder="@sergey, @anna_impro" value={members} onChange={(e) => setMembers(e.currentTarget.value)} />
          <Group><Button loading={saving} onClick={() => perform(
            () => api(teamId ? `/api/miniapp/teams/${teamId}` : "/api/miniapp/teams", { method: teamId ? "PATCH" : "POST", body: JSON.stringify({ name: teamName, members }) }),
            teamId ? "Команда обновлена" : "Команда создана",
          ).then(() => { setTeamId(null); setTeamName(""); setMembers(""); })}>{teamId ? "Сохранить" : "Добавить"}</Button>{teamId && <Button variant="subtle" onClick={() => { setTeamId(null); setTeamName(""); setMembers(""); }}>Отмена</Button>}</Group>
        </Stack></Paper>
      </Stack></Tabs.Panel>
      <Tabs.Panel value="venues" pt="lg"><Stack>
        {options.venues.map((venue) => <Paper className="resource-card" key={venue.id}><Text fw={750}>{venue.name}</Text><Text size="sm" c="dimmed">{venue.city} · {venue.defaultSeats} мест</Text></Paper>)}
        <Paper className="resource-form"><Stack><Title order={3}>Новая площадка</Title><TextInput label="Название" value={venueName} onChange={(e) => setVenueName(e.currentTarget.value)} /><SimpleGrid cols={2}><TextInput label="Город" value={venueCity} onChange={(e) => setVenueCity(e.currentTarget.value)} /><NumberInput min={1} label="Мест" value={venueSeats} onChange={(next) => setVenueSeats(typeof next === "number" ? next : 1)} /></SimpleGrid><TextInput type="url" label="Ссылка на карту" value={venueUrl} onChange={(e) => setVenueUrl(e.currentTarget.value)} /><Button loading={saving} onClick={() => perform(() => api("/api/miniapp/venues", { method: "POST", body: JSON.stringify({ name: venueName, city: venueCity, mapsUrl: venueUrl, defaultSeats: venueSeats }) }), "Площадка добавлена").then(() => { setVenueName(""); setVenueUrl(""); })}>Добавить площадку</Button></Stack></Paper>
      </Stack></Tabs.Panel>
      <Tabs.Panel value="channels" pt="lg"><Stack>
        {options.adChannels.map((item) => <Paper className="resource-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.username}</Text><Text size="sm" c="dimmed">{item.isActive ? "Активен" : "Отключён"}</Text></div><Switch checked={item.isActive} onChange={() => perform(() => api(`/api/miniapp/ad-channels/${item.id}/toggle`, { method: "PATCH" }), "Канал обновлён")} /></Group></Paper>)}
        <Paper className="resource-form"><Stack><Title order={3}>Новый рекламный канал</Title><TextInput label="Telegram-ник канала" placeholder="@afisha_cyprus" value={channel} onChange={(e) => setChannel(e.currentTarget.value)} /><Button loading={saving} onClick={() => perform(() => api("/api/miniapp/ad-channels", { method: "POST", body: JSON.stringify({ username: channel }) }), "Канал добавлен").then(() => setChannel(""))}>Добавить канал</Button></Stack></Paper>
      </Stack></Tabs.Panel>
      <Tabs.Panel value="access" pt="lg"><Stack>
        <Paper className="resource-form"><Stack><Title order={3}>Пригласить организатора</Title><Text size="sm" c="dimmed">Ссылка одноразовая и автоматически истечёт. Новый пользователь сможет управлять только созданными им афишами.</Text><Button loading={saving} onClick={() => void createInvite()}>Создать ссылку</Button>{inviteUrl && <><Text size="sm" style={{ wordBreak: "break-all" }}>{inviteUrl}</Text><Button variant="light" onClick={() => void copyInvite()}>Копировать приглашение</Button></>}</Stack></Paper>
        <Title order={3}>Пользователи с доступом</Title>
        {accessLoading && <Loader size="sm" />}
        {!accessLoading && accessUsers.map((user) => <Paper className="resource-card" key={user.id}><Group justify="space-between" align="flex-start"><div><Group gap="xs"><Text fw={750}>{[user.firstName, user.lastName].filter(Boolean).join(" ") || user.username || user.telegramId}</Text><Badge color={user.role === "admin" ? "yellow" : "violet"}>{user.role === "admin" ? "Администратор" : "Организатор"}</Badge>{user.isCurrent && <Badge color="gray">Вы</Badge>}</Group>{user.username && <Anchor size="sm" href={`https://t.me/${user.username}`} target="_blank">@{user.username}</Anchor>}</div>{!user.isProtected && !user.isCurrent && <Button size="xs" color="red" variant="subtle" onClick={() => setRevokeUser(user)}>Отозвать</Button>}</Group></Paper>)}
        {!accessLoading && !accessUsers.length && <Text c="dimmed">Пользователей с доступом нет.</Text>}
      </Stack></Tabs.Panel>
      <Tabs.Panel value="audit" pt="lg"><Stack>
        <Group justify="space-between"><div><Title order={3}>Журнал действий</Title><Text size="sm" c="dimmed">Последние 100 административных операций Mini App</Text></div><Button size="xs" variant="light" loading={auditLoading} onClick={() => void loadAudit()}>Обновить</Button></Group>
        {auditLoading && !auditItems.length && <Loader size="sm" />}
        {auditItems.map((item) => {
          const labels: Record<string, string> = { "show.published": "Афиша опубликована", "show.republished": "Афиша опубликована повторно", "show.cancelled": "Афиша отменена", "show.cloned": "Создана копия афиши", "access.invite_created": "Создано приглашение", "access.role_changed": "Изменена роль пользователя" };
          const actorName = item.actor?.username ? `@${item.actor.username}` : item.actor?.firstName || "Удалённый пользователь";
          return <Paper className="resource-card" key={item.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{labels[item.action] ?? item.action}</Text><Text size="sm" c="dimmed">{actorName} · {new Date(item.createdAt).toLocaleString("ru-RU")}</Text></div><Badge variant="light">{item.entityType} #{item.entityId ?? "—"}</Badge></Group>{item.details && <Text size="xs" c="dimmed" mt="sm" style={{ wordBreak: "break-word" }}>{Object.entries(item.details).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</Text>}</Paper>;
        })}
        {!auditLoading && !auditItems.length && <Text c="dimmed">Журнал пока пуст.</Text>}
      </Stack></Tabs.Panel>
    </Tabs>
    <Modal opened={revokeUser !== null} onClose={() => setRevokeUser(null)} title="Отозвать доступ?" centered><Text>Пользователь {revokeUser?.username ? `@${revokeUser.username}` : revokeUser?.firstName} больше не сможет открывать Mini App и управлять афишами.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setRevokeUser(null)}>Отмена</Button><Button color="red" loading={saving} onClick={() => void confirmRevoke()}>Отозвать</Button></Group></Modal>
  </Modal>;
}

const previewAttendees: Attendees = {
  occupied: 6, maxSeats: 50, arrived: 3, hasMore: false, nextOffset: 100,
  registrations: [
    { id: 1, name: "Анна Смирнова", guests: 1, username: "anna_impro", confirmed: true, checkedInCount: 2, source: "telegram" },
    { id: 2, name: "Михаил Орлов", guests: 0, username: "m_orlov", confirmed: null, checkedInCount: 0, source: "telegram" },
  ],
  manual: [{ id: 11, name: "Елена", contact: "@elena_cy", checkedInCount: 1, source: "manual" }],
};

function AttendeesModal({ opened, onClose, show, demo }: { opened: boolean; onClose: () => void; show: Show; demo: boolean }) {
  const [data, setData] = React.useState<Attendees | null>(demo ? previewAttendees : null);
  const [loading, setLoading] = React.useState(!demo);
  const [manualRows, setManualRows] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState<{ kind: "registration" | "manual"; id: number; name: string } | null>(null);

  const load = React.useCallback(async () => {
    if (demo) { setData(previewAttendees); return; }
    setLoading(true);
    try { setData(await api<Attendees>(`/api/miniapp/shows/${show.id}/attendees`)); }
    catch (reason) { notifications.show({ color: "red", title: "Не удалось загрузить записи", message: (reason as Error).message }); }
    finally { setLoading(false); }
  }, [demo, show.id]);

  React.useEffect(() => { if (opened) void load(); }, [opened, load]);

  async function mutate(key: string, path: string, method: string, body?: object) {
    setBusy(key);
    try {
      await api(path, { method, body: body ? JSON.stringify(body) : undefined });
      if (!demo) await load();
      notifications.show({ color: "violet", title: "Список обновлён", message: "Изменения сохранены" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось изменить запись", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function addManual() {
    const rows = manualRows.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
      const [name, contact] = line.split("|", 2).map((part) => part.trim()); return { name, contact: contact || null };
    });
    if (!rows.length) return;
    setBusy("add");
    try {
      await api(`/api/miniapp/shows/${show.id}/attendees/manual`, { method: "POST", body: JSON.stringify({ rows }) });
      setManualRows(""); if (!demo) await load();
      notifications.show({ color: "violet", title: "Зрители добавлены", message: `Добавлено: ${rows.length}` });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось добавить", message: (reason as Error).message }); }
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

  return <Modal opened={opened} onClose={onClose} title={`Записи · ${show.title}`} fullScreen>
    {loading && <Stack><Skeleton height={100} /><Skeleton height={100} /></Stack>}
    {data && <Stack gap="md">
      <Paper className="attendance-summary"><Group justify="space-between"><div><Text size="sm" c="dimmed">Записано</Text><Title order={2}>{data.occupied} / {data.maxSeats}</Title></div><div><Text size="sm" c="dimmed">Пришли</Text><Title order={2}>{data.arrived}</Title></div></Group><Progress value={Math.min(100, data.occupied / Math.max(1, data.maxSeats) * 100)} mt="md" color="violet" /></Paper>
      <Title order={3}>Записались через бот</Title>
      {data.registrations.map((item) => <Paper className="attendee-card" key={item.id}><Stack gap="sm"><Group justify="space-between" align="flex-start"><div><Text fw={750}>{item.name}{item.guests ? ` +${item.guests}` : ""}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}</div><Badge color={item.checkedInCount ? "green" : "gray"}>{item.checkedInCount} / {item.guests + 1}</Badge></Group><Group justify="space-between"><Group gap="xs"><Button size="xs" variant="light" disabled={item.checkedInCount <= 0 || busy !== null} onClick={() => mutate(`check-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount - 1 })}>− Пришли</Button><Button size="xs" variant="light" disabled={item.checkedInCount >= item.guests + 1 || busy !== null} onClick={() => mutate(`check-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount + 1 })}>+ Пришли</Button></Group><Button size="xs" color="red" variant="subtle" loading={busy === `cancel-${item.id}`} onClick={() => setConfirmDelete({ kind: "registration", id: item.id, name: item.name })}>Отменить</Button></Group><Group gap="xs"><Text size="sm" c="dimmed">Гостей:</Text><Button size="compact-xs" variant="default" disabled={item.guests <= 0 || busy !== null} onClick={() => mutate(`guest-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { guests: item.guests - 1 })}>−</Button><Text>{item.guests}</Text><Button size="compact-xs" variant="default" disabled={item.guests >= 50 || busy !== null} onClick={() => mutate(`guest-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { guests: item.guests + 1 })}>+</Button></Group></Stack></Paper>)}
      <Title order={3}>Добавлены вручную</Title>
      {data.manual.map((item) => <Paper className="attendee-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.name}</Text>{item.contact && <Text size="sm" c="dimmed">{item.contact}</Text>}</div><Group gap="xs"><Button size="xs" color={item.checkedInCount ? "green" : "gray"} variant="light" loading={busy === `manual-${item.id}`} onClick={() => mutate(`manual-${item.id}`, `/api/miniapp/shows/${show.id}/manual-attendees/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount ? 0 : 1 })}>{item.checkedInCount ? "Пришёл ✓" : "Отметить"}</Button><Button size="xs" color="red" variant="subtle" loading={busy === `delete-${item.id}`} onClick={() => setConfirmDelete({ kind: "manual", id: item.id, name: item.name })}>Удалить</Button></Group></Group></Paper>)}
      <Paper className="resource-form"><Stack><Title order={3}>Добавить вручную</Title><Textarea autosize minRows={4} description="Один зритель на строку, контакт через |" placeholder={"Иван Иванов | @ivan\nМария Петрова"} value={manualRows} onChange={(event) => setManualRows(event.currentTarget.value)} /><Button loading={busy === "add"} onClick={addManual}>Добавить зрителей</Button></Stack></Paper>
      {data.hasMore && <Alert color="yellow">Показаны первые 100 записей. Пагинацию добавим в следующем проходе.</Alert>}
    </Stack>}
    <Modal opened={confirmDelete !== null} onClose={() => setConfirmDelete(null)} title="Подтвердить действие" centered>
      <Text>Удалить запись «{confirmDelete?.name}»? Это освободит место в афише.</Text>
      <Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setConfirmDelete(null)}>Не удалять</Button><Button color="red" onClick={removeConfirmed}>Удалить</Button></Group>
    </Modal>
  </Modal>;
}

function AnnouncementModal({ opened, onClose, show, demo }: { opened: boolean; onClose: () => void; show: Show; demo: boolean }) {
  const [html, setHtml] = React.useState("");
  const [imageUrl, setImageUrl] = React.useState<string | null>(null);
  const [poster, setPoster] = React.useState<File | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [publishing, setPublishing] = React.useState(false);
  const [promotion, setPromotion] = React.useState<Promotion | null>(null);
  const [repeatConfirm, setRepeatConfirm] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      if (demo) {
        const demoHtml = `🎭 <b>${show.title}</b><br>👥 Команда: ${show.teamName}<br><br>📅 ${show.showDateLabel}<br>📍 ${show.location}, ${show.city}<br><br>👥 Записаться тут: <b>через бота</b> или у @${show.registrarUsername ?? "ответственного"}`;
        setHtml(demoHtml);
        setPromotion({ html: demoHtml, text: `${show.title}\n${show.showDateLabel}\nhttps://t.me/ImprovCypEventBot?start=show_${show.id}`, registrationUrl: `https://t.me/ImprovCypEventBot?start=show_${show.id}`, hasPoster: false, hasPublished: false, channels: [{ id: 1, username: "limassol_events", url: "https://t.me/limassol_events" }] });
      } else {
        const preview = await api<Promotion>(`/api/miniapp/shows/${show.id}/promotion`);
        setPromotion(preview);
        setHtml(preview.html.split("\n").join("<br>"));
        if (preview.hasPoster) {
          const blob = await authenticatedBlob(`/api/miniapp/shows/${show.id}/poster`);
          setImageUrl(URL.createObjectURL(blob));
        }
      }
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось открыть предпросмотр", message: (reason as Error).message }); }
    finally { setLoading(false); }
  }, [demo, show]);

  React.useEffect(() => {
    if (opened) void load();
    return () => { if (imageUrl) URL.revokeObjectURL(imageUrl); };
  }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload() {
    if (!poster) return;
    setLoading(true);
    try {
      if (!demo) {
        const body = new FormData(); body.append("poster", poster);
        await api(`/api/miniapp/shows/${show.id}/poster`, { method: "POST", body });
      }
      if (imageUrl) URL.revokeObjectURL(imageUrl);
      setImageUrl(URL.createObjectURL(poster)); setPoster(null);
      notifications.show({ color: "violet", title: "Изображение обновлено", message: "Новая афиша сохранена" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось загрузить", message: (reason as Error).message }); }
    finally { setLoading(false); }
  }

  async function publish(repeat = false) {
    setPublishing(true);
    try {
      if (!demo) {
        const idempotencyKey = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
        await api(`/api/miniapp/shows/${show.id}/publish`, {
          method: "POST",
          body: JSON.stringify(repeat ? { repeat: true, confirmed: true, idempotencyKey } : {}),
        });
      }
      setPromotion((current) => current ? { ...current, hasPublished: true } : current);
      setRepeatConfirm(false);
      notifications.show({ color: "green", title: repeat ? "Анонс отправлен повторно" : "Анонс опубликован", message: "Пост отправлен в основной канал с кнопкой записи" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось опубликовать", message: (reason as Error).message }); }
    finally { setPublishing(false); }
  }

  async function copyPromotion() {
    if (!promotion) return;
    try {
      await navigator.clipboard.writeText(promotion.text);
      notifications.show({ color: "green", title: "Скопировано", message: "Текст содержит прямую ссылку на запись" });
    } catch { notifications.show({ color: "red", title: "Не удалось скопировать", message: "Выдели текст анонса вручную" }); }
  }

  return <Modal opened={opened} onClose={onClose} title="Предпросмотр анонса" fullScreen>
    <Stack gap="md">
      {loading && <Skeleton height={240} radius="lg" />}
      {!loading && imageUrl && <img className="poster-preview" src={imageUrl} alt={`Афиша ${show.title}`} />}
      {!loading && <Paper className="telegram-preview" dangerouslySetInnerHTML={{ __html: html }} />}
      {!loading && promotion && <Paper className="resource-form"><Stack>
        <Title order={3}>Публикация</Title>
        {!promotion.hasPublished ?
          <Button loading={publishing} disabled={!promotion.hasPoster && !demo} onClick={() => void publish()}>Опубликовать в основном канале</Button> :
          <><Alert color="green">Анонс уже публиковался в основном канале.</Alert><Button color="orange" variant="light" onClick={() => setRepeatConfirm(true)}>Отправить повторно</Button></>}
        {!promotion.hasPoster && !demo && <Text size="sm" c="dimmed">Для публикации сначала загрузите изображение афиши.</Text>}
      </Stack></Paper>}
      {!loading && promotion && <Paper className="resource-form"><Stack>
        <Title order={3}>Рекламные каналы</Title>
        <Text size="sm" c="dimmed">При копировании Telegram не переносит inline-кнопку. Поэтому в текст добавлена прямая ссылка на запись — она останется кликабельной.</Text>
        <Button variant="light" onClick={() => void copyPromotion()}>Скопировать текст и ссылку</Button>
        {promotion.channels.length ? promotion.channels.map((channel) => <Button key={channel.id} component="a" href={channel.url} target="_blank" variant="default">Открыть @{channel.username.replace(/^@/, "")}</Button>) : <Text size="sm" c="dimmed">Активные рекламные каналы пока не добавлены.</Text>}
      </Stack></Paper>}
      <Paper className="resource-form"><Stack><FileInput accept="image/jpeg,image/png,image/webp" label="Изображение афиши" description="JPEG, PNG или WebP, до 8 МБ" value={poster} onChange={setPoster} clearable /><Button disabled={!poster} loading={loading} onClick={upload}>Загрузить изображение</Button></Stack></Paper>
    </Stack>
    <Modal opened={repeatConfirm} onClose={() => setRepeatConfirm(false)} title="Повторить публикацию?" centered>
      <Text>В основной канал будет отправлена ещё одна полноценная афиша с кнопкой записи.</Text>
      <Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setRepeatConfirm(false)}>Отмена</Button><Button color="orange" loading={publishing} onClick={() => void publish(true)}>Да, отправить повторно</Button></Group>
    </Modal>
  </Modal>;
}

function AnalyticsModal({ opened, onClose, show, demo }: { opened: boolean; onClose: () => void; show: Show; demo: boolean }) {
  const [data, setData] = React.useState<Analytics | null>(null);
  const [loading, setLoading] = React.useState(false);
  React.useEffect(() => {
    if (!opened) return;
    setLoading(true);
    const demoData: Analytics = {
      registered: show.occupiedSeats, capacity: show.maxSeats, cancelledRegistrations: 4,
      confirmed: 27, arrived: 25, checkinEnabled: true, feedbackEnabled: true,
      feedbackCount: 18, averageRating: 4.7, ratingDistribution: { "5": 14, "4": 3, "3": 1 },
      sources: [{ source: "direct", count: 20 }, { source: "instagram", count: 9 }, { source: "manual", count: 5 }],
      comments: [{ id: 1, rating: 5, comment: "Очень тёплое и смешное шоу!", username: "viewer", name: "Анна", createdAt: new Date().toISOString() }], commentsLimit: 100,
    };
    (demo ? Promise.resolve(demoData) : api<Analytics>(`/api/miniapp/shows/${show.id}/analytics`))
      .then(setData)
      .catch((reason: Error) => notifications.show({ color: "red", title: "Не удалось загрузить аналитику", message: reason.message }))
      .finally(() => setLoading(false));
  }, [opened, show, demo]);
  const sourceLabels: Record<string, string> = { direct: "Через бота", manual: "Вручную", social: "Другие соцсети", instagram: "Instagram", channel: "Telegram-канал", team: "Команда" };
  const maxRating = data ? Math.max(1, ...Object.values(data.ratingDistribution)) : 1;
  async function downloadCsv() {
    try {
      if (demo) {
        notifications.show({ color: "gray", title: "Демо-режим", message: "Экспорт доступен после запуска из Telegram" });
        return;
      }
      const blob = await authenticatedBlob(`/api/miniapp/shows/${show.id}/export.csv`);
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = `show-${show.id}-attendees.csv`; link.click(); URL.revokeObjectURL(url);
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось скачать CSV", message: (reason as Error).message }); }
  }
  return <Modal opened={opened} onClose={onClose} title={`Аналитика · ${show.title}`} fullScreen>
    {loading && <Stack><Skeleton height={120} radius="lg" /><Skeleton height={220} radius="lg" /></Stack>}
    {!loading && data && <Stack>
      <Button variant="light" onClick={() => void downloadCsv()}>Скачать зрителей и отзывы · CSV</Button>
      <SimpleGrid cols={2}>
        <Paper className="resource-card"><Text size="sm" c="dimmed">Записано</Text><Title order={2}>{data.registered} / {data.capacity}</Title></Paper>
        <Paper className="resource-card"><Text size="sm" c="dimmed">Пришли</Text><Title order={2}>{data.checkinEnabled ? data.arrived : "—"}</Title></Paper>
        <Paper className="resource-card"><Text size="sm" c="dimmed">Подтвердили</Text><Title order={2}>{data.confirmed}</Title></Paper>
        <Paper className="resource-card"><Text size="sm" c="dimmed">Отмен записей</Text><Title order={2}>{data.cancelledRegistrations}</Title></Paper>
      </SimpleGrid>
      <Paper className="resource-form"><Stack><Title order={3}>Источники записей</Title>{data.sources.length ? data.sources.map((item) => <div key={item.source}><Group justify="space-between"><Text>{sourceLabels[item.source] ?? item.source}</Text><Text fw={700}>{item.count}</Text></Group><Progress value={data.registered ? item.count / data.registered * 100 : 0} mt={5} /></div>) : <Text c="dimmed">Данных пока нет</Text>}</Stack></Paper>
      <Paper className="resource-form"><Stack><Group justify="space-between"><Title order={3}>Отзывы</Title><Badge color="yellow" size="lg">★ {data.averageRating.toFixed(1)} · {data.feedbackCount}</Badge></Group>
        {!data.feedbackEnabled && <Alert color="gray">Сбор отзывов для этой афиши выключен.</Alert>}
        {[5, 4, 3, 2, 1].map((rating) => <Group key={rating} wrap="nowrap"><Text w={28}>{rating}★</Text><Progress value={(data.ratingDistribution[String(rating)] ?? 0) / maxRating * 100} style={{ flex: 1 }} color="yellow" /><Text w={24} ta="right">{data.ratingDistribution[String(rating)] ?? 0}</Text></Group>)}
      </Stack></Paper>
      <Title order={3}>Комментарии</Title>
      {data.comments.length ? data.comments.map((item) => <Paper className="resource-card" key={item.id}><Group justify="space-between" align="flex-start"><div><Text fw={700}>{item.name}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}</div><Badge color="yellow">{item.rating} ★</Badge></Group><Text mt="sm" style={{ whiteSpace: "pre-wrap" }}>{item.comment}</Text></Paper>) : <Text c="dimmed">Текстовых отзывов пока нет.</Text>}
    </Stack>}
  </Modal>;
}

function App() {
  const isPreview = import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1";
  const [shows, setShows] = React.useState<Show[]>(isPreview ? previewShows : []);
  const [selected, setSelected] = React.useState<Show | null>(null);
  const [status, setStatus] = React.useState<"upcoming" | "past">("upcoming");
  const [loading, setLoading] = React.useState(!isPreview);
  const [error, setError] = React.useState<string | null>(null);
  const [options, setOptions] = React.useState<Options>({ teams: [], venues: [], adChannels: [] });
  const [me, setMe] = React.useState<Me | null>(isPreview ? { id: 1, firstName: "Sergey", username: "sergey", role: "admin" } : null);
  const [formOpened, setFormOpened] = React.useState(false);
  const [managementOpened, setManagementOpened] = React.useState(false);
  const [attendeesOpened, setAttendeesOpened] = React.useState(false);
  const [announcementOpened, setAnnouncementOpened] = React.useState(false);
  const [analyticsOpened, setAnalyticsOpened] = React.useState(false);
  const [toolsOpened, setToolsOpened] = React.useState(false);
  const [editing, setEditing] = React.useState<Show | null>(null);

  React.useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready();
    tg?.expand();
    if (tg?.colorScheme) document.documentElement.dataset.theme = tg.colorScheme;
  }, []);

  React.useEffect(() => {
    if (!isPreview) { api<Options>("/api/miniapp/options").then(setOptions).catch(() => undefined); api<Me>("/api/miniapp/me").then(setMe).catch(() => undefined); }
    else setOptions({ teams: [{ id: 1, name: "T·IMPRO", members: "@sergey, @anna_impro" }, { id: 2, name: "Импровизаторы Кипра", members: null }], venues: [{ id: 1, name: "Ravens Music Hall", city: "Лимасол", mapsUrl: "https://maps.example", defaultSeats: 50 }], adChannels: [{ id: 1, username: "@afisha_cyprus", isActive: true }] });
  }, [isPreview]);

  function reloadShows() {
    if (isPreview) return;
    setLoading(true);
    api<{ items: Show[] }>(`/api/miniapp/shows?status=${status}`).then(({ items }) => setShows(items)).finally(() => setLoading(false));
  }

  async function reloadOptions() {
    if (isPreview) return;
    setOptions(await api<Options>("/api/miniapp/options"));
  }

  React.useEffect(() => {
    if (isPreview) return;
    setLoading(true);
    setError(null);
    api<{ items: Show[] }>(`/api/miniapp/shows?status=${status}`)
      .then(({ items }) => setShows(items))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [status, isPreview]);

  async function openShow(show: Show) {
    setSelected(show);
    if (isPreview) return;
    try {
      setSelected(await api<Show>(`/api/miniapp/shows/${show.id}`));
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  if (selected) {
    const fill = Math.min(100, Math.round(selected.occupiedSeats / Math.max(1, selected.maxSeats) * 100));
    const registrationUrl = selected.registrationUrl ?? `https://t.me/ImprovCypEventBot?start=show_${selected.id}`;
    return <main className="shell">
      <Button className="back" variant="subtle" onClick={() => setSelected(null)}>← Все афиши</Button>
      <Paper className="detail-card">
        <div className="eyebrow">{selected.teamName}</div>
        <Title order={1}>{selected.title}</Title>
        <Text className="date">{selected.showDateLabel}</Text>
        <Text className="place">{selected.location} · {selected.city}</Text>
        <div className="capacity-head"><span>Записи</span><strong>{selected.occupiedSeats} / {selected.maxSeats}</strong></div>
        <Progress value={fill} color="violet" mt={8} />
        {selected.registrarUsername && <Anchor className="registrar" href={`https://t.me/${selected.registrarUsername}`} target="_blank">Ответственный · @{selected.registrarUsername} ↗</Anchor>}
        {selected.posterText && <Text className="poster-text">{selected.posterText}</Text>}
      </Paper>
      {!selected.isActive && <Alert color="red" mt="md">Эта афиша отменена. Новые записи недоступны.</Alert>}
      <SimpleGrid cols={2} mt="md"><Button variant="light" onClick={() => setAttendeesOpened(true)}>Зрители</Button><Button variant="light" onClick={() => setAnnouncementOpened(true)}>Анонс</Button><Button variant="light" onClick={() => setAnalyticsOpened(true)}>Аналитика</Button><Button variant="light" onClick={() => setToolsOpened(true)}>Ссылка и QR</Button><Button onClick={() => { setEditing(selected); setFormOpened(true); }}>Изменить</Button></SimpleGrid>
      <AttendeesModal opened={attendeesOpened} onClose={() => setAttendeesOpened(false)} show={selected} demo={isPreview} />
      <AnnouncementModal opened={announcementOpened} onClose={() => setAnnouncementOpened(false)} show={selected} demo={isPreview} />
      <AnalyticsModal opened={analyticsOpened} onClose={() => setAnalyticsOpened(false)} show={selected} demo={isPreview} />
      <ShowToolsModal opened={toolsOpened} onClose={() => setToolsOpened(false)} show={selected} registrationUrl={registrationUrl} demo={isPreview} onChanged={(next) => { setSelected(next); reloadShows(); }} />
      <ShowForm opened={formOpened} initial={editing} options={options} onClose={() => setFormOpened(false)} onSaved={() => { setFormOpened(false); setSelected(null); reloadShows(); }} />
    </main>;
  }

  return <main className="shell">
    <header>
      <div><div className="brand">T·IMPRO</div><h1>Мои афиши</h1>{isPreview && <Badge mt={8} color="gray" variant="light">Демо-данные · API отключён</Badge>}</div>
      <button className="avatar" onClick={() => setManagementOpened(true)} aria-label="Открыть настройки">⚙</button>
    </header>
    <Tabs value={status} onChange={(value) => setStatus(value as "upcoming" | "past")} className="tabs">
      <Tabs.List grow><Tabs.Tab value="upcoming">Будущие</Tabs.Tab><Tabs.Tab value="past">Прошедшие</Tabs.Tab></Tabs.List>
    </Tabs>
    {loading && <Stack gap="sm" aria-label="Загружаем афиши"><Skeleton height={184} radius="lg" /><Skeleton height={184} radius="lg" /><Group justify="center"><Loader color="violet" size="sm" /></Group></Stack>}
    {error && <Alert color="red" title="Не удалось открыть панель">{error}</Alert>}
    {!loading && !error && shows.length === 0 && <Paper className="state"><Title order={3}>Здесь пока пусто</Title><Text>Создать первую афишу пока можно в боте.</Text></Paper>}
    <section className="show-list">
      {shows.map((show) => {
        const fill = Math.min(100, Math.round(show.occupiedSeats / Math.max(1, show.maxSeats) * 100));
        return <Paper component="button" className="show-card" key={show.id} onClick={() => openShow(show)}>
          <div className="card-top"><Badge color="violet" variant="light">{show.showDateLabel}</Badge><span className="arrow">→</span></div>
          <Title order={2}>{show.title}</Title><Text>{show.teamName}</Text><Text className="muted">{show.location} · {show.city}</Text>
          <div className="capacity-head"><span>Заполнено</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></div>
          <Progress value={fill} color="violet" mt={8} />
        </Paper>;
      })}
    </section>
    <Button className="primary" fullWidth onClick={() => { setEditing(null); setFormOpened(true); }}>＋ Создать афишу</Button>
    <ShowForm opened={formOpened} initial={editing} options={options} onClose={() => setFormOpened(false)} onSaved={() => { setFormOpened(false); reloadShows(); }} />
    <ManagementModal opened={managementOpened} onClose={() => setManagementOpened(false)} me={me} options={options} reload={reloadOptions} />
  </main>;
}

function ShowToolsModal({ opened, onClose, show, registrationUrl, demo, onChanged }: {
  opened: boolean; onClose: () => void; show: Show; registrationUrl: string; demo: boolean; onChanged: (show: Show) => void;
}) {
  const cloneDefault = React.useMemo(() => {
    const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  }, []);
  const [cloneDate, setCloneDate] = React.useState(cloneDefault);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [cancelConfirm, setCancelConfirm] = React.useState(false);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(registrationUrl);
      notifications.show({ color: "green", title: "Ссылка скопирована", message: "Её можно вставить в любой пост или сообщение" });
    } catch { notifications.show({ color: "red", title: "Не удалось скопировать", message: registrationUrl }); }
  }

  async function downloadQr() {
    setBusy("qr");
    try {
      const blob = demo ? new Blob() : await authenticatedBlob(`/api/miniapp/shows/${show.id}/qr`);
      if (!demo) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a"); link.href = url; link.download = `show-${show.id}-qr.png`; link.click();
        URL.revokeObjectURL(url);
      }
      notifications.show({ color: "green", title: "QR-код готов", message: demo ? "В демо скачивание отключено" : "PNG сохранён на устройство" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось получить QR", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function clone() {
    setBusy("clone");
    try {
      const result = await api<{ id: number }>(`/api/miniapp/shows/${show.id}/clone`, { method: "POST", body: JSON.stringify({ showDateLocal: cloneDate }) });
      notifications.show({ color: "green", title: "Копия создана", message: `Новая афиша #${result.id} сохранена на выбранную дату` });
      onClose();
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось создать копию", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function cancelShow() {
    setBusy("cancel");
    try {
      const result = demo ? { sent: 12, failed: 0 } : await api<{ sent: number; failed: number }>(`/api/miniapp/shows/${show.id}/cancel`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
      onChanged({ ...show, isActive: false }); setCancelConfirm(false); onClose();
      notifications.show({ color: result.failed ? "yellow" : "green", title: "Афиша отменена", message: `Уведомления: доставлено ${result.sent}, ошибок ${result.failed}` });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось отменить афишу", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  return <Modal opened={opened} onClose={onClose} title="Ссылка и действия" fullScreen>
    <Stack>
      <Paper className="resource-form"><Stack><Title order={3}>Ссылка на запись</Title><Text size="sm" style={{ wordBreak: "break-all" }}>{registrationUrl}</Text><Group grow><Button variant="light" onClick={() => void copyLink()}>Копировать</Button><Button loading={busy === "qr"} onClick={() => void downloadQr()}>Скачать QR</Button></Group></Stack></Paper>
      <Paper className="resource-form"><Stack><Title order={3}>Создать похожую афишу</Title><TextInput type="datetime-local" label="Дата и время новой афиши" value={cloneDate} onChange={(event) => setCloneDate(event.currentTarget.value)} /><Button loading={busy === "clone"} onClick={() => void clone()}>Создать копию</Button></Stack></Paper>
      {show.isActive && <Paper className="resource-form"><Stack><Title order={3}>Опасная зона</Title><Text size="sm" c="dimmed">Запись будет закрыта. Если афиша публиковалась, в канал уйдёт сообщение об отмене, а записавшиеся получат уведомление.</Text><Button color="red" variant="light" onClick={() => setCancelConfirm(true)}>Отменить афишу</Button></Stack></Paper>}
    </Stack>
    <Modal opened={cancelConfirm} onClose={() => setCancelConfirm(false)} title="Точно отменить афишу?" centered><Text>Действие закроет новые записи и отправит уведомления зрителям.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setCancelConfirm(false)}>Не отменять</Button><Button color="red" loading={busy === "cancel"} onClick={() => void cancelShow()}>Да, отменить</Button></Group></Modal>
  </Modal>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark"><Notifications /><App /></MantineProvider>
  </React.StrictMode>,
);
