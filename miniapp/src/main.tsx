import React from "react";
import ReactDOM from "react-dom/client";
import {
  Alert, Anchor, Autocomplete, Badge, Button, Collapse, FileInput, Group, Loader, MantineProvider, Modal, NumberInput,
  Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text,
  Textarea, TextInput, Title, createTheme,
} from "@mantine/core";
import { DateTimePicker, DatesProvider } from "@mantine/dates";
import { Notifications, notifications } from "@mantine/notifications";
import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/notifications/styles.css";
import "dayjs/locale/ru";
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
  registrationChatId?: number | null;
  registrationChatTitle?: string | null;
  registrationChatNameMode?: "short" | "full";
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
  primaryColor: "gray",
  defaultRadius: "md",
  colors: {
    dark: [
      "#fafafa", "#f5f5f5", "#e5e5e5", "#a3a3a3", "#737373",
      "#525252", "#303030", "#242424", "#171717", "#0f0f0f",
    ],
  },
  fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  headings: { fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
});

function telegramHaptic(kind: "selection" | "light" = "selection") {
  const haptic = window.Telegram?.WebApp.HapticFeedback;
  if (kind === "selection") haptic?.selectionChanged();
  else haptic?.impactOccurred("light");
}

function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const demoMutation = import.meta.env.DEV &&
    new URLSearchParams(location.search).get("preview") === "1" &&
    init.method && init.method !== "GET";
  if (demoMutation) return Promise.resolve({ id: Date.now(), isActive: true } as T);
  const initData = window.Telegram?.WebApp.initData ?? "";
  if (!initData) {
    return Promise.reject(new Error("Telegram не передал данные авторизации. Закрой Mini App и открой его свежей кнопкой из админ-бота."));
  }
  const isForm = init.body instanceof FormData;
  return fetch(path, {
    ...init,
    headers: { ...(!isForm && { "Content-Type": "application/json" }), Authorization: `tma ${initData}`, ...init.headers },
  }).then(async (response) => {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const requestId = response.headers.get("X-Request-ID") ?? payload.requestId;
      const message = response.status === 401 ? "Открой Mini App из админ-бота" :
        response.status === 403 ? "Недостаточно прав для этого действия" :
        payload.field ? `Проверь поле: ${payload.field}` : "Не удалось выполнить запрос";
      throw new Error(`${message}${requestId ? ` · код ${requestId}` : ""}`);
    }
    return response.json() as Promise<T>;
  });
}

async function authenticatedBlob(path: string): Promise<Blob> {
  const initData = window.Telegram?.WebApp.initData ?? "";
  if (!initData) throw new Error("Telegram не передал данные авторизации");
  const response = await fetch(path, { headers: { Authorization: `tma ${initData}` } });
  if (!response.ok) {
    const requestId = response.headers.get("X-Request-ID");
    throw new Error(`Не удалось загрузить файл${requestId ? ` · код ${requestId}` : ""}`);
  }
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

function ShowForm({ opened, initial, options, me, reloadOptions, onClose, onSaved }: {
  opened: boolean; initial: Show | null; options: Options; me: Me | null;
  reloadOptions: () => Promise<void>; onClose: () => void; onSaved: (id: number) => void;
}) {
  const [value, setValue] = React.useState<ShowFormValue>(emptyForm());
  const [venueId, setVenueId] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [teamModal, setTeamModal] = React.useState(false);
  const [venueModal, setVenueModal] = React.useState(false);
  const [newTeamName, setNewTeamName] = React.useState("");
  const [newTeamMembers, setNewTeamMembers] = React.useState("");
  const [newVenueName, setNewVenueName] = React.useState("");
  const [newVenueCity, setNewVenueCity] = React.useState("Лимасол");
  const [newVenueUrl, setNewVenueUrl] = React.useState("");
  const [newVenueSeats, setNewVenueSeats] = React.useState(50);
  const [poster, setPoster] = React.useState<File | null>(null);
  const [notifyViewers, setNotifyViewers] = React.useState(false);
  const [chatTarget, setChatTarget] = React.useState("");
  const [chatNameMode, setChatNameMode] = React.useState<"short" | "full">("short");
  const [verifiedChat, setVerifiedChat] = React.useState<{ id: number; title: string; target: string } | null>(null);
  const [checkingChat, setCheckingChat] = React.useState(false);
  const [chatSetupOpened, setChatSetupOpened] = React.useState(false);
  const [previewOpened, setPreviewOpened] = React.useState(false);
  React.useEffect(() => {
    if (!opened) return;
    const nextValue = initial ? formFromShow(initial) : emptyForm();
    const venue = initial
      ? options.venues.find((item) => item.name === initial.location && item.city === initial.city)
      : undefined;
    if (venue) nextValue.locationUrl = venue.mapsUrl ?? "";
    setValue(nextValue);
    setVenueId(venue ? String(venue.id) : initial ? "__custom__" : null);
    setPoster(null); setNotifyViewers(false); setChatTarget(""); setChatNameMode("short"); setVerifiedChat(null); setChatSetupOpened(false); setPreviewOpened(false);
  }, [opened, initial, options.venues]);
  const set = <K extends keyof ShowFormValue>(key: K, next: ShowFormValue[K]) => setValue((current) => ({ ...current, [key]: next }));
  const selectedVenue = options.venues.find((item) => String(item.id) === venueId);
  const registrarOptions = React.useMemo(() => {
    const team = options.teams.find((item) => item.name === value.teamName);
    const splitMembers = (members: string | null) => (members ?? "").split(/[\s,;]+/)
      .map((username) => username.trim())
      .filter(Boolean)
      .map((username) => username.startsWith("@") ? username : `@${username}`);
    const usernames = [
      ...splitMembers(team?.members ?? null),
      ...options.teams.filter((item) => item.id !== team?.id).flatMap((item) => splitMembers(item.members)),
    ];
    if (me?.username) usernames.unshift(`@${me.username}`);
    return [...new Set(usernames)];
  }, [me?.username, options.teams, value.teamName]);
  const normalizedRegistrar = value.registrarUsername.trim().replace(/^@?/, "@");
  const registrarIsValid = /^@[A-Za-z][A-Za-z0-9_]{4,31}$/.test(normalizedRegistrar);

  function showPayload(): ShowFormValue {
    return selectedVenue
      ? { ...value, location: selectedVenue.name, city: selectedVenue.city, locationUrl: selectedVenue.mapsUrl ?? "", maxSeats: selectedVenue.defaultSeats }
      : value;
  }

  function selectVenue(id: string | null) {
    if (id === "__new__") { setVenueModal(true); return; }
    setVenueId(id);
    const venue = options.venues.find((item) => String(item.id) === id);
    if (venue) setValue((current) => ({ ...current, location: venue.name, city: venue.city, locationUrl: venue.mapsUrl ?? "", maxSeats: venue.defaultSeats }));
    else if (id === "__custom__") setValue((current) => ({ ...current, location: "", locationUrl: "" }));
  }

  async function createTeam() {
    setSaving(true);
    try {
      await api("/api/miniapp/teams", { method: "POST", body: JSON.stringify({ name: newTeamName, members: newTeamMembers }) });
      set("teamName", newTeamName.trim());
      setTeamModal(false); setNewTeamName(""); setNewTeamMembers("");
      await reloadOptions();
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось создать команду", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  async function createVenue() {
    setSaving(true);
    try {
      const result = await api<{ id: number }>("/api/miniapp/venues", { method: "POST", body: JSON.stringify({ name: newVenueName, city: newVenueCity, mapsUrl: newVenueUrl, defaultSeats: newVenueSeats }) });
      setVenueId(String(result.id));
      setValue((current) => ({ ...current, location: newVenueName.trim(), city: newVenueCity.trim(), locationUrl: newVenueUrl.trim(), maxSeats: newVenueSeats }));
      setVenueModal(false); setNewVenueName(""); setNewVenueUrl("");
      await reloadOptions();
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось создать площадку", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  async function verifyRegistrationChat() {
    const target = chatTarget.trim();
    if (!target) return;
    setCheckingChat(true);
    try {
      const result = await api<{ id: number; title: string }>("/api/miniapp/registration-chat/verify", { method: "POST", body: JSON.stringify({ target }) });
      setVerifiedChat({ ...result, target });
      notifications.show({ color: "green", title: "Чат проверен", message: `${result.title}: бот подключён` });
    } catch (reason) {
      setVerifiedChat(null);
      notifications.show({ color: "red", title: "Чат не прошёл проверку", message: (reason as Error).message });
    } finally { setCheckingChat(false); }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!initial && chatTarget.trim() && verifiedChat?.target !== chatTarget.trim()) {
      notifications.show({ color: "red", title: "Сначала проверь чат записей", message: "Бот должен быть добавлен в выбранный чат" });
      return;
    }
    setSaving(true);
    try {
      const payload = showPayload();
      const result = await api<{ id: number; notified?: number; failed?: number }>(initial ? `/api/miniapp/shows/${initial.id}` : "/api/miniapp/shows", {
        method: initial ? "PATCH" : "POST", body: JSON.stringify(initial ? { ...payload, notify: notifyViewers } : payload),
      });
      let posterError: Error | null = null;
      let chatError: Error | null = null;
      if (!initial && verifiedChat) {
        try {
          await api(`/api/miniapp/shows/${result.id}/registration-chat`, { method: "PUT", body: JSON.stringify({ target: String(verifiedChat.id), nameMode: chatNameMode }) });
        } catch (reason) {
          chatError = reason as Error;
        }
      }
      if (poster) {
        const form = new FormData(); form.append("poster", poster);
        try {
          await api(`/api/miniapp/shows/${result.id}/poster`, { method: "POST", body: form });
        } catch (reason) {
          posterError = reason as Error;
        }
      }
      notifications.show(posterError || chatError
        ? { color: "yellow", title: initial ? "Афиша обновлена частично" : "Афиша создана частично", message: [posterError && "Изображение не загружено", chatError && "Чат записей не подключён"].filter(Boolean).join(" · ") }
        : { color: "gray", title: initial ? "Афиша обновлена" : "Афиша создана", message: "Изменения сохранены" });
      onSaved(result.id);
    } catch (reason) {
      notifications.show({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message });
    } finally { setSaving(false); }
  }

  async function sendPreview() {
    setSaving(true);
    try {
      await api("/api/miniapp/shows/preview", { method: "POST", body: JSON.stringify(showPayload()) });
      notifications.show({ color: "green", title: "Превью отправлено", message: "Проверь сообщение в админ-боте" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось отправить превью", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  return <Modal opened={opened} onClose={onClose} title={initial ? "Редактировать афишу" : "Новая афиша"} fullScreen>
    <form onSubmit={submit} className="show-form">
      <Stack gap="md">
        <TextInput required label="Название" value={value.title} onChange={(e) => set("title", e.currentTarget.value)} maxLength={256} />
        <Select required searchable allowDeselect={false} label="Команда" data={[...options.teams.map((team) => ({ value: team.name, label: team.name })), { value: "__new__", label: "＋ Добавить новую команду" }]} value={value.teamName || null} onChange={(next) => next === "__new__" ? setTeamModal(true) : set("teamName", next ?? "")} />
        <DateTimePicker required size="lg" dropdownType="modal" label="Дата и время" valueFormat="D MMMM YYYY, HH:mm" locale="ru" minDate={new Date().toISOString().slice(0, 10)} value={value.showDateLocal.replace("T", " ")} onChange={(next) => set("showDateLocal", next?.replace(" ", "T") ?? "")} timePickerProps={{ minutesStep: 5 }} clearable={false} className="large-date-picker" />
        <Select required searchable allowDeselect={false} label="Площадка" placeholder="Выбери площадку" data={[...options.venues.map((venue) => ({ value: String(venue.id), label: `${venue.name} · ${venue.city}` })), { value: "__custom__", label: "Другая площадка" }, ...(me?.role === "admin" ? [{ value: "__new__", label: "＋ Добавить новую площадку" }] : [])]} value={venueId} onChange={selectVenue} />
        {selectedVenue && <Paper className="venue-summary"><Text fw={700}>{selectedVenue.name}</Text><Text size="sm">{selectedVenue.city} · {selectedVenue.defaultSeats} мест</Text>{selectedVenue.mapsUrl && <Anchor href={selectedVenue.mapsUrl} target="_blank" size="sm">Открыть на карте ↗</Anchor>}</Paper>}
        {venueId === "__custom__" && <><TextInput required label="Название площадки" value={value.location} onChange={(e) => set("location", e.currentTarget.value)} maxLength={512} /><SimpleGrid cols={2}><Autocomplete required label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={value.city} onChange={(next) => set("city", next)} /><NumberInput required min={1} max={10000} label="Количество мест" value={value.maxSeats} onChange={(next) => set("maxSeats", typeof next === "number" ? next : 1)} /></SimpleGrid><TextInput type="url" label="Ссылка на карту" value={value.locationUrl} onChange={(e) => set("locationUrl", e.currentTarget.value)} /></>}
        <Autocomplete
          label="Ответственный в Telegram"
          placeholder="@username"
          data={registrarOptions}
          value={value.registrarUsername}
          onChange={(next) => set("registrarUsername", next)}
          onBlur={() => value.registrarUsername.trim() && set("registrarUsername", normalizedRegistrar)}
          maxLength={33}
          error={value.registrarUsername && !registrarIsValid ? "Проверь ник: от 5 до 32 латинских букв, цифр или _" : undefined}
          description={registrarIsValid ? <Anchor href={`https://t.me/${normalizedRegistrar.slice(1)}`} target="_blank" size="xs">Проверить профиль в Telegram ↗</Anchor> : "Можно выбрать участника любой команды или ввести другой ник"}
        />
        {!initial && <div className="optional-section"><Button type="button" fullWidth variant="light" onClick={() => setChatSetupOpened((opened) => !opened)} aria-expanded={chatSetupOpened}>{chatSetupOpened ? "Скрыть настройку чата" : "＋ Настроить чат записей"}</Button><Collapse expanded={chatSetupOpened}><Paper className="venue-summary"><Stack gap="sm"><div><Text fw={700}>Чат записей <Text component="span" c="dimmed" fw={400}>(необязательно)</Text></Text><Text size="sm" c="dimmed">Бот будет писать сюда о каждой новой записи.</Text></div><TextInput label="Канал или группа" placeholder="@registrations_chat или −100…" value={chatTarget} onChange={(event) => { setChatTarget(event.currentTarget.value); setVerifiedChat(null); }} /><Select label="Как показывать имя" value={chatNameMode} onChange={(next) => setChatNameMode((next as "short" | "full") ?? "short")} data={[{ value: "short", label: "Сокращённо" }, { value: "full", label: "Полностью" }]} /><Button type="button" variant="light" disabled={!chatTarget.trim()} loading={checkingChat} onClick={() => void verifyRegistrationChat()}>{verifiedChat ? `Проверено: ${verifiedChat.title} ✓` : "Проверить чат и бота"}</Button></Stack></Paper></Collapse></div>}
        <Textarea label="Текст афиши" autosize minRows={5} maxLength={1800} value={value.posterText} onChange={(e) => set("posterText", e.currentTarget.value)} />
        <FileInput accept="image/jpeg,image/png,image/webp" label="Изображение афиши" description={initial?.hasPoster ? "Выбери файл, чтобы заменить текущее изображение" : "JPEG, PNG или WebP, до 8 МБ"} value={poster} onChange={setPoster} clearable />
        <Switch label="Включить check-in" checked={value.checkinEnabled} onChange={(e) => set("checkinEnabled", e.currentTarget.checked)} />
        <Switch label="Запрашивать отзывы после шоу" checked={value.feedbackEnabled} onChange={(e) => set("feedbackEnabled", e.currentTarget.checked)} />
        {initial && <Switch label="Уведомить записавшихся об изменениях" checked={notifyViewers} onChange={(event) => setNotifyViewers(event.currentTarget.checked)} />}
        <div className="optional-section"><Button type="button" fullWidth variant="light" onClick={() => setPreviewOpened((opened) => !opened)} aria-expanded={previewOpened}>{previewOpened ? "Скрыть предпросмотр" : "Показать предпросмотр"}</Button><Collapse expanded={previewOpened}><Paper className="telegram-preview"><Text size="xs" fw={800} c="dimmed">ПРЕДПРОСМОТР</Text><Title order={3}>🎭 {value.title || "Название шоу"}</Title><Text>👥 Команда: {value.teamName || "не выбрана"}</Text><Text>📅 {value.showDateLocal ? new Date(value.showDateLocal).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" }) : "дата не выбрана"}</Text><Text>📍 {selectedVenue?.name || value.location || "площадка не выбрана"}, {selectedVenue?.city || value.city}</Text>{value.registrarUsername && <Text>👤 Ответственный: {value.registrarUsername}</Text>}{value.posterText && <Text mt="sm" style={{ whiteSpace: "pre-wrap" }}>{value.posterText}</Text>}</Paper></Collapse></div>
        <Button variant="light" loading={saving} disabled={!value.title || !value.teamName || !value.showDateLocal || !venueId} onClick={() => void sendPreview()}>Отправить тест в админ-бот</Button>
        <Button type="submit" loading={saving} size="md" disabled={!initial && Boolean(chatTarget.trim()) && !verifiedChat}>{initial ? "Сохранить изменения" : "Создать афишу"}</Button>
      </Stack>
    </form>
    <Modal opened={teamModal} onClose={() => setTeamModal(false)} title="Новая команда" centered><Stack><TextInput required label="Название" value={newTeamName} onChange={(e) => setNewTeamName(e.currentTarget.value)} /><Textarea label="Telegram-ники участников" value={newTeamMembers} onChange={(e) => setNewTeamMembers(e.currentTarget.value)} /><Button disabled={!newTeamName.trim()} loading={saving} onClick={() => void createTeam()}>Создать и выбрать</Button></Stack></Modal>
    <Modal opened={venueModal} onClose={() => setVenueModal(false)} title="Новая площадка" centered><Stack><TextInput required label="Название" value={newVenueName} onChange={(e) => setNewVenueName(e.currentTarget.value)} /><Autocomplete required label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={newVenueCity} onChange={setNewVenueCity} /><NumberInput required min={1} max={10000} label="Количество мест" value={newVenueSeats} onChange={(next) => setNewVenueSeats(typeof next === "number" ? next : 1)} /><TextInput type="url" label="Ссылка на карту" value={newVenueUrl} onChange={(e) => setNewVenueUrl(e.currentTarget.value)} /><Button disabled={!newVenueName.trim() || !newVenueCity.trim()} loading={saving} onClick={() => void createVenue()}>Сохранить для всех и выбрать</Button></Stack></Modal>
  </Modal>;
}

function ManagementModal({ opened, onClose, me, options, reload }: {
  opened: boolean; onClose: () => void; me: Me | null; options: Options; reload: () => Promise<void>;
}) {
  const [teamId, setTeamId] = React.useState<number | null>(null);
  const [teamName, setTeamName] = React.useState("");
  const [members, setMembers] = React.useState("");
  const [venueName, setVenueName] = React.useState("");
  const [venueId, setVenueId] = React.useState<number | null>(null);
  const [venueCity, setVenueCity] = React.useState("Лимасол");
  const [venueUrl, setVenueUrl] = React.useState("");
  const [venueSeats, setVenueSeats] = React.useState(50);
  const [channel, setChannel] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [teamEditorOpened, setTeamEditorOpened] = React.useState(false);
  const [venueEditorOpened, setVenueEditorOpened] = React.useState(false);
  const [channelEditorOpened, setChannelEditorOpened] = React.useState(false);
  const [accessUsers, setAccessUsers] = React.useState<AccessUser[]>([]);
  const [accessLoading, setAccessLoading] = React.useState(false);
  const [inviteUrl, setInviteUrl] = React.useState<string | null>(null);
  const [revokeUser, setRevokeUser] = React.useState<AccessUser | null>(null);
  const [auditItems, setAuditItems] = React.useState<AuditItem[]>([]);
  const [auditLoading, setAuditLoading] = React.useState(false);
  const [auditOpened, setAuditOpened] = React.useState(false);
  const [auditError, setAuditError] = React.useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<{ kind: "team" | "venue" | "channel"; id: number; name: string } | null>(null);

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
    setAuditError(null);
    try {
      const preview = import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1";
      if (preview) setAuditItems([
        { id: 1, action: "show.published", entityType: "show", entityId: 1, details: { messageId: 123 }, createdAt: new Date().toISOString(), actor: { id: 1, username: "sergey", firstName: "Sergey", lastName: null, telegramId: 416607535 } },
        { id: 2, action: "access.invite_created", entityType: "invite", entityId: 5, details: { role: "organizer" }, createdAt: new Date(Date.now() - 3600000).toISOString(), actor: { id: 1, username: "sergey", firstName: "Sergey", lastName: null, telegramId: 416607535 } },
      ]); else setAuditItems((await api<{ items: AuditItem[] }>("/api/miniapp/audit-log")).items);
    } catch (reason) { const message = (reason as Error).message; setAuditError(message); notifications.show({ color: "red", title: "Не удалось загрузить журнал", message }); }
    finally { setAuditLoading(false); }
  }, [me?.role]);

  async function perform(action: () => Promise<unknown>, success: string) {
    setSaving(true);
    try {
      await action(); await reload();
      notifications.show({ color: "gray", title: success, message: "Справочник обновлён" });
      return true;
    } catch (reason) {
      notifications.show({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message });
      return false;
    } finally { setSaving(false); }
  }

  function editTeam(team: Options["teams"][number]) {
    setTeamId(team.id); setTeamName(team.name); setMembers(team.members ?? ""); setTeamEditorOpened(true);
  }

  function editVenue(venue: Options["venues"][number]) {
    setVenueId(venue.id); setVenueName(venue.name); setVenueCity(venue.city);
    setVenueUrl(venue.mapsUrl ?? ""); setVenueSeats(venue.defaultSeats); setVenueEditorOpened(true);
  }

  async function confirmResourceDelete() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    const paths = { team: "teams", venue: "venues", channel: "ad-channels" };
    const saved = await perform(() => api(`/api/miniapp/${paths[target.kind]}/${target.id}`, { method: "DELETE" }), "Удалено");
    if (saved) setDeleteTarget(null);
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

  return <Modal opened={opened} onClose={onClose} title="Настройки" fullScreen>
    <Tabs defaultValue="teams" className="settings-tabs" variant="pills">
      <Tabs.List grow><Tabs.Tab value="teams">Команды</Tabs.Tab>{me?.role === "admin" && <Tabs.Tab value="venues">Площадки</Tabs.Tab>}{me?.role === "admin" && <Tabs.Tab value="channels">Каналы</Tabs.Tab>}{me?.role === "admin" && <Tabs.Tab value="access">Доступ</Tabs.Tab>}</Tabs.List>
      <Tabs.Panel value="teams" pt="lg"><Stack>
        {options.teams.map((team) => <Paper className="resource-card" key={team.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{team.name}</Text><Text size="sm" c="dimmed">{team.members || "Участники не указаны"}</Text></div><Group gap="xs"><Button size="xs" variant="light" onClick={() => editTeam(team)}>Изменить</Button><Button size="xs" color="red" variant="subtle" onClick={() => setDeleteTarget({ kind: "team", id: team.id, name: team.name })}>Удалить</Button></Group></Group></Paper>)}
        <Button variant="light" onClick={() => { setTeamId(null); setTeamName(""); setMembers(""); setTeamEditorOpened(true); }}>＋ Добавить команду</Button>
      </Stack></Tabs.Panel>
      <Tabs.Panel value="venues" pt="lg"><Stack>
        {options.venues.map((venue) => <Paper className="resource-card" key={venue.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{venue.name}</Text><Text size="sm" c="dimmed">{venue.city} · {venue.defaultSeats} мест</Text></div><Group gap="xs"><Button size="xs" variant="light" onClick={() => editVenue(venue)}>Изменить</Button><Button size="xs" color="red" variant="subtle" onClick={() => setDeleteTarget({ kind: "venue", id: venue.id, name: venue.name })}>Удалить</Button></Group></Group></Paper>)}
        <Button variant="light" onClick={() => { setVenueId(null); setVenueName(""); setVenueUrl(""); setVenueEditorOpened(true); }}>＋ Добавить площадку</Button>
      </Stack></Tabs.Panel>
      <Tabs.Panel value="channels" pt="lg"><Stack>
        {options.adChannels.map((item) => <Paper className="resource-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.username}</Text><Text size="sm" c="dimmed">{item.isActive ? "Активен" : "Отключён"}</Text></div><Group gap="xs"><Switch checked={item.isActive} onChange={() => perform(() => api(`/api/miniapp/ad-channels/${item.id}/toggle`, { method: "PATCH" }), "Канал обновлён")} /><Button size="xs" color="red" variant="subtle" onClick={() => setDeleteTarget({ kind: "channel", id: item.id, name: item.username })}>Удалить</Button></Group></Group></Paper>)}
        <Button variant="light" onClick={() => setChannelEditorOpened(true)}>＋ Добавить канал</Button>
      </Stack></Tabs.Panel>
      <Tabs.Panel value="access" pt="lg"><Stack>
        <Paper className="resource-form"><Stack><Title order={3}>Пригласить организатора</Title><Text size="sm" c="dimmed">Ссылка одноразовая и автоматически истечёт. Новый пользователь сможет управлять только созданными им афишами.</Text><Button loading={saving} onClick={() => void createInvite()}>Создать ссылку</Button>{inviteUrl && <><Text size="sm" style={{ wordBreak: "break-all" }}>{inviteUrl}</Text><Button variant="light" onClick={() => void copyInvite()}>Копировать приглашение</Button></>}</Stack></Paper>
        <Title order={3}>Пользователи с доступом</Title>
        {accessLoading && <Loader size="sm" />}
        {!accessLoading && accessUsers.map((user) => <Paper className="resource-card" key={user.id}><Group justify="space-between" align="flex-start"><div><Group gap="xs"><Text fw={750}>{[user.firstName, user.lastName].filter(Boolean).join(" ") || user.username || user.telegramId}</Text><Badge color={user.role === "admin" ? "yellow" : "gray"}>{user.role === "admin" ? "Администратор" : "Организатор"}</Badge>{user.isCurrent && <Badge color="gray">Вы</Badge>}</Group>{user.username && <Anchor size="sm" href={`https://t.me/${user.username}`} target="_blank">@{user.username}</Anchor>}</div>{!user.isProtected && !user.isCurrent && <Button size="xs" color="red" variant="subtle" onClick={() => setRevokeUser(user)}>Отозвать</Button>}</Group></Paper>)}
        {!accessLoading && !accessUsers.length && <Text c="dimmed">Пользователей с доступом нет.</Text>}
        <Button variant="default" onClick={() => { setAuditOpened(true); void loadAudit(); }}>Журнал действий</Button>
      </Stack></Tabs.Panel>
    </Tabs>
    <Modal opened={teamEditorOpened} onClose={() => setTeamEditorOpened(false)} title={teamId ? "Редактировать команду" : "Новая команда"} centered><Stack><TextInput label="Название" value={teamName} onChange={(e) => setTeamName(e.currentTarget.value)} /><Textarea label="Telegram-ники участников" description="Через запятую или с новой строки" placeholder="@sergey, @anna_impro" value={members} onChange={(e) => setMembers(e.currentTarget.value)} /><Button disabled={!teamName.trim()} loading={saving} onClick={() => perform(() => api(teamId ? `/api/miniapp/teams/${teamId}` : "/api/miniapp/teams", { method: teamId ? "PATCH" : "POST", body: JSON.stringify({ name: teamName, members }) }), teamId ? "Команда обновлена" : "Команда создана").then((saved) => { if (saved) { setTeamEditorOpened(false); setTeamId(null); setTeamName(""); setMembers(""); } })}>{teamId ? "Сохранить" : "Добавить"}</Button></Stack></Modal>
    <Modal opened={venueEditorOpened} onClose={() => setVenueEditorOpened(false)} title={venueId ? "Редактировать площадку" : "Новая площадка"} centered><Stack><TextInput label="Название" value={venueName} onChange={(e) => setVenueName(e.currentTarget.value)} /><SimpleGrid cols={2}><Autocomplete label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={venueCity} onChange={setVenueCity} /><NumberInput min={1} label="Мест" value={venueSeats} onChange={(next) => setVenueSeats(typeof next === "number" ? next : 1)} /></SimpleGrid><TextInput type="url" label="Ссылка на карту" value={venueUrl} onChange={(e) => setVenueUrl(e.currentTarget.value)} /><Button disabled={!venueName.trim() || !venueCity.trim()} loading={saving} onClick={() => perform(() => api(venueId ? `/api/miniapp/venues/${venueId}` : "/api/miniapp/venues", { method: venueId ? "PATCH" : "POST", body: JSON.stringify({ name: venueName, city: venueCity, mapsUrl: venueUrl, defaultSeats: venueSeats }) }), venueId ? "Площадка обновлена" : "Площадка добавлена").then((saved) => { if (saved) { setVenueEditorOpened(false); setVenueId(null); setVenueName(""); setVenueUrl(""); } })}>{venueId ? "Сохранить" : "Добавить площадку"}</Button></Stack></Modal>
    <Modal opened={channelEditorOpened} onClose={() => setChannelEditorOpened(false)} title="Новый рекламный канал" centered><Stack><TextInput label="Telegram-ник канала" placeholder="@afisha_cyprus" value={channel} onChange={(e) => setChannel(e.currentTarget.value)} /><Button disabled={!channel.trim()} loading={saving} onClick={() => perform(() => api("/api/miniapp/ad-channels", { method: "POST", body: JSON.stringify({ username: channel }) }), "Канал добавлен").then((saved) => { if (saved) { setChannelEditorOpened(false); setChannel(""); } })}>Добавить канал</Button></Stack></Modal>
    <Modal opened={auditOpened} onClose={() => setAuditOpened(false)} title="Журнал действий" fullScreen><Stack>
        <Group justify="space-between"><div><Title order={3}>Журнал действий</Title><Text size="sm" c="dimmed">Последние 100 административных операций Mini App</Text></div><Button size="xs" variant="light" loading={auditLoading} onClick={() => void loadAudit()}>Обновить</Button></Group>
        {auditError && <Alert color="red" title="Не удалось загрузить журнал">{auditError}<Button mt="sm" size="xs" variant="light" color="red" onClick={() => void loadAudit()}>Повторить</Button></Alert>}
        {auditLoading && !auditItems.length && <Loader size="sm" />}
        {auditItems.map((item) => {
          const labels: Record<string, string> = { "show.published": "Афиша опубликована", "show.republished": "Афиша опубликована повторно", "show.cancelled": "Афиша отменена", "show.cloned": "Создана копия афиши", "access.invite_created": "Создано приглашение", "access.role_changed": "Изменена роль пользователя" };
          const actorName = item.actor?.username ? `@${item.actor.username}` : item.actor?.firstName || "Удалённый пользователь";
          return <Paper className="resource-card" key={item.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{labels[item.action] ?? item.action}</Text><Text size="sm" c="dimmed">{actorName} · {new Date(item.createdAt).toLocaleString("ru-RU")}</Text></div><Badge variant="light">{item.entityType} #{item.entityId ?? "—"}</Badge></Group>{item.details && <Text size="xs" c="dimmed" mt="sm" style={{ wordBreak: "break-word" }}>{Object.entries(item.details).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</Text>}</Paper>;
        })}
        {!auditLoading && !auditItems.length && <Text c="dimmed">Журнал пока пуст.</Text>}
      </Stack></Modal>
    <Modal opened={revokeUser !== null} onClose={() => setRevokeUser(null)} title="Отозвать доступ?" centered><Text>Пользователь {revokeUser?.username ? `@${revokeUser.username}` : revokeUser?.firstName} больше не сможет открывать Mini App и управлять афишами.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setRevokeUser(null)}>Отмена</Button><Button color="red" loading={saving} onClick={() => void confirmRevoke()}>Отозвать</Button></Group></Modal>
    <Modal opened={deleteTarget !== null} onClose={() => setDeleteTarget(null)} title="Удалить безвозвратно?" centered><Text>«{deleteTarget?.name}» будет удалено из справочника.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setDeleteTarget(null)}>Отмена</Button><Button color="red" loading={saving} onClick={() => void confirmResourceDelete()}>Удалить</Button></Group></Modal>
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
  const [search, setSearch] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = React.useState<{ kind: "registration" | "manual"; id: number; name: string } | null>(null);

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

  async function mutate(key: string, path: string, method: string, body?: object) {
    setBusy(key);
    try {
      await api(path, { method, body: body ? JSON.stringify(body) : undefined });
      if (!demo) await load(0);
      notifications.show({ color: "gray", title: "Список обновлён", message: "Изменения сохранены" });
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
      setManualRows(""); if (!demo) await load(0);
      notifications.show({ color: "gray", title: "Зрители добавлены", message: `Добавлено: ${rows.length}` });
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
      <Paper className="attendance-summary"><Group justify="space-between"><div><Text size="sm" c="dimmed">Записано</Text><Title order={2}>{data.occupied} / {data.maxSeats}</Title></div><div><Text size="sm" c="dimmed">Пришли</Text><Title order={2}>{data.arrived}</Title></div></Group><Progress value={Math.min(100, data.occupied / Math.max(1, data.maxSeats) * 100)} mt="md" color="gray" /></Paper>
      <Group gap="xs" wrap="nowrap"><TextInput style={{ flex: 1 }} aria-label="Поиск зрителя" placeholder="Имя или @username" value={search} onChange={(event) => setSearch(event.currentTarget.value)} onKeyDown={(event) => { if (event.key === "Enter") void load(0); }} /><Button variant="light" loading={loading} onClick={() => void load(0)}>Найти</Button></Group>
      <Title order={3}>Записались через бот</Title>
      {data.registrations.map((item) => <Paper className="attendee-card" key={item.id}><Stack gap="sm"><Group justify="space-between" align="flex-start"><div><Text fw={750}>{item.name}{item.guests ? ` +${item.guests}` : ""}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}</div><Badge color={item.checkedInCount ? "green" : "gray"}>{item.checkedInCount} / {item.guests + 1}</Badge></Group><Group justify="space-between"><Group gap="xs"><Button size="xs" variant="light" disabled={item.checkedInCount <= 0 || busy !== null} onClick={() => mutate(`check-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount - 1 })}>− Пришли</Button><Button size="xs" variant="light" disabled={item.checkedInCount >= item.guests + 1 || busy !== null} onClick={() => mutate(`check-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount + 1 })}>+ Пришли</Button></Group><Button size="xs" color="red" variant="subtle" loading={busy === `cancel-${item.id}`} onClick={() => setConfirmDelete({ kind: "registration", id: item.id, name: item.name })}>Отменить</Button></Group><Group gap="xs"><Text size="sm" c="dimmed">Гостей:</Text><Button size="compact-xs" variant="default" disabled={item.guests <= 0 || busy !== null} onClick={() => mutate(`guest-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { guests: item.guests - 1 })}>−</Button><Text>{item.guests}</Text><Button size="compact-xs" variant="default" disabled={item.guests >= 50 || busy !== null} onClick={() => mutate(`guest-${item.id}`, `/api/miniapp/shows/${show.id}/registrations/${item.id}`, "PATCH", { guests: item.guests + 1 })}>+</Button></Group></Stack></Paper>)}
      <Title order={3}>Добавлены вручную</Title>
      {data.manual.map((item) => <Paper className="attendee-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.name}</Text>{item.contact && <Text size="sm" c="dimmed">{item.contact}</Text>}</div><Group gap="xs"><Button size="xs" color={item.checkedInCount ? "green" : "gray"} variant="light" loading={busy === `manual-${item.id}`} onClick={() => mutate(`manual-${item.id}`, `/api/miniapp/shows/${show.id}/manual-attendees/${item.id}`, "PATCH", { checkedInCount: item.checkedInCount ? 0 : 1 })}>{item.checkedInCount ? "Пришёл ✓" : "Отметить"}</Button><Button size="xs" color="red" variant="subtle" loading={busy === `delete-${item.id}`} onClick={() => setConfirmDelete({ kind: "manual", id: item.id, name: item.name })}>Удалить</Button></Group></Group></Paper>)}
      <Paper className="resource-form"><Stack><Title order={3}>Добавить вручную</Title><Textarea autosize minRows={4} description="Один зритель на строку, контакт через |" placeholder={"Иван Иванов | @ivan\nМария Петрова"} value={manualRows} onChange={(event) => setManualRows(event.currentTarget.value)} /><Button loading={busy === "add"} onClick={addManual}>Добавить зрителей</Button></Stack></Paper>
      {data.hasMore && <Button variant="default" loading={loading} onClick={() => void load(data.nextOffset, true)}>Показать ещё</Button>}
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
      notifications.show({ color: "gray", title: "Изображение обновлено", message: "Новая афиша сохранена" });
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
  const [error, setError] = React.useState<string | null>(null);
  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const demoData: Analytics = {
      registered: show.occupiedSeats, capacity: show.maxSeats, cancelledRegistrations: 4,
      confirmed: 27, arrived: 25, checkinEnabled: true, feedbackEnabled: true,
      feedbackCount: 18, averageRating: 4.7, ratingDistribution: { "5": 14, "4": 3, "3": 1 },
      sources: [{ source: "direct", count: 20 }, { source: "instagram", count: 9 }, { source: "manual", count: 5 }],
      comments: [{ id: 1, rating: 5, comment: "Очень тёплое и смешное шоу!", username: "viewer", name: "Анна", createdAt: new Date().toISOString() }], commentsLimit: 100,
    };
    try {
      setData(demo ? demoData : await api<Analytics>(`/api/miniapp/shows/${show.id}/analytics`));
    } catch (reason) {
      const message = (reason as Error).message;
      setData(null); setError(message);
      notifications.show({ color: "red", title: "Не удалось загрузить аналитику", message });
    } finally { setLoading(false); }
  }, [show.id, show.maxSeats, show.occupiedSeats, demo]);
  React.useEffect(() => { if (opened) void load(); }, [opened, load]);
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
    {!loading && error && <Alert color="red" title="Не удалось загрузить аналитику">{error}<Button mt="sm" size="xs" variant="light" color="red" onClick={() => void load()}>Повторить</Button></Alert>}
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
  const [teamFilter, setTeamFilter] = React.useState<string | null>(null);
  const [yearFilter, setYearFilter] = React.useState<string | null>(null);
  const [filtersOpened, setFiltersOpened] = React.useState(false);
  const [showsHasMore, setShowsHasMore] = React.useState(false);
  const [showsNextOffset, setShowsNextOffset] = React.useState(0);
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
  const [toolsMode, setToolsMode] = React.useState<"all" | "chat">("all");
  const [descriptionOpened, setDescriptionOpened] = React.useState(false);
  const [editing, setEditing] = React.useState<Show | null>(null);

  const hasBackTarget = Boolean(selected || formOpened || managementOpened || attendeesOpened || announcementOpened || analyticsOpened || toolsOpened);

  React.useEffect(() => {
    const backButton = window.Telegram?.WebApp.BackButton;
    if (!backButton) return;
    const goBack = () => {
      telegramHaptic("light");
      if (toolsOpened) setToolsOpened(false);
      else if (analyticsOpened) setAnalyticsOpened(false);
      else if (announcementOpened) setAnnouncementOpened(false);
      else if (attendeesOpened) setAttendeesOpened(false);
      else if (formOpened) { setFormOpened(false); setEditing(null); }
      else if (managementOpened) setManagementOpened(false);
      else if (selected) setSelected(null);
    };
    backButton.onClick(goBack);
    if (hasBackTarget) backButton.show(); else backButton.hide();
    return () => backButton.offClick(goBack);
  }, [analyticsOpened, announcementOpened, attendeesOpened, formOpened, hasBackTarget, managementOpened, selected, toolsOpened]);

  React.useEffect(() => {
    const settingsButton = window.Telegram?.WebApp.SettingsButton;
    if (!settingsButton) return;
    const openSettings = () => { telegramHaptic("selection"); setManagementOpened(true); };
    settingsButton.onClick(openSettings);
    settingsButton.show();
    return () => { settingsButton.offClick(openSettings); settingsButton.hide(); };
  }, []);

  React.useEffect(() => {
    if (!isPreview) { api<Options>("/api/miniapp/options").then(setOptions).catch(() => undefined); api<Me>("/api/miniapp/me").then(setMe).catch(() => undefined); }
    else setOptions({ teams: [{ id: 1, name: "T·IMPRO", members: "@sergey, @anna_impro" }, { id: 2, name: "Импровизаторы Кипра", members: null }], venues: [{ id: 1, name: "Ravens Music Hall", city: "Лимасол", mapsUrl: "https://maps.example", defaultSeats: 50 }], adChannels: [{ id: 1, username: "@afisha_cyprus", isActive: true }] });
  }, [isPreview]);

  function reloadShows(offset = 0, append = false) {
    if (isPreview) return;
    setLoading(true);
    const query = new URLSearchParams({ status, offset: String(offset) });
    if (teamFilter) query.set("team", teamFilter);
    if (yearFilter) query.set("year", yearFilter);
    api<{ items: Show[]; hasMore: boolean; nextOffset: number }>(`/api/miniapp/shows?${query}`)
      .then(({ items, hasMore, nextOffset }) => {
        setShows((current) => append ? [...current, ...items] : items);
        setShowsHasMore(hasMore); setShowsNextOffset(nextOffset);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }

  async function reloadOptions() {
    if (isPreview) return;
    setOptions(await api<Options>("/api/miniapp/options"));
  }

  React.useEffect(() => {
    if (isPreview) return;
    setLoading(true);
    setError(null);
    reloadShows();
  }, [status, teamFilter, yearFilter, isPreview]);

  async function openShow(show: Show) {
    setDescriptionOpened(false);
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
      <Button className="back" variant="subtle" onClick={() => { telegramHaptic("light"); setSelected(null); }}>← Все афиши</Button>
      <section className="show-detail">
        <div className="eyebrow">{selected.teamName}</div>
        <Title order={1}>{selected.title}</Title>
        <Text className="date">{selected.showDateLabel}</Text>
        {selected.locationUrl ? <Anchor className="place-link" href={selected.locationUrl} target="_blank">{selected.location} · {selected.city} ↗</Anchor> : <Text className="place">{selected.location} · {selected.city}</Text>}
        <div className="capacity-head"><span>Записи</span><strong>{selected.occupiedSeats} / {selected.maxSeats}</strong></div>
        <Progress value={fill} color="gray" mt={8} />
        {selected.registrarUsername && <Anchor className="registrar" href={`https://t.me/${selected.registrarUsername}`} target="_blank">Ответственный · @{selected.registrarUsername} ↗</Anchor>}
        {selected.posterText && <div className="description-block"><Button variant="subtle" size="xs" onClick={() => setDescriptionOpened((opened) => !opened)} aria-expanded={descriptionOpened}>{descriptionOpened ? "Скрыть описание" : "Показать описание"}</Button><Collapse expanded={descriptionOpened}><Text className="poster-text">{selected.posterText}</Text></Collapse></div>}
      </section>
      {!selected.isActive && <Alert color="red" mt="md">Эта афиша отменена. Новые записи недоступны.</Alert>}
      <div className="show-actions">
        <Button className="primary" fullWidth onClick={() => setAttendeesOpened(true)}>Зрители · {selected.occupiedSeats}</Button>
        <SimpleGrid cols={2}><Button variant="light" onClick={() => { setEditing(selected); setFormOpened(true); }}>Изменить</Button><Button variant="light" onClick={() => setAnnouncementOpened(true)}>Анонс</Button><Button variant="light" onClick={() => setAnalyticsOpened(true)}>Аналитика</Button><Button variant="light" onClick={() => { setToolsMode("chat"); setToolsOpened(true); }}>Чат{selected.registrationChatId ? " ✓" : ""}</Button></SimpleGrid>
        <Button fullWidth variant="subtle" onClick={() => { setToolsMode("all"); setToolsOpened(true); }}>Ещё действия</Button>
      </div>
      <AttendeesModal opened={attendeesOpened} onClose={() => setAttendeesOpened(false)} show={selected} demo={isPreview} />
      <AnnouncementModal opened={announcementOpened} onClose={() => setAnnouncementOpened(false)} show={selected} demo={isPreview} />
      <AnalyticsModal opened={analyticsOpened} onClose={() => setAnalyticsOpened(false)} show={selected} demo={isPreview} />
      <ShowToolsModal mode={toolsMode} opened={toolsOpened} onClose={() => setToolsOpened(false)} show={selected} registrationUrl={registrationUrl} demo={isPreview} onChanged={(next) => { setSelected(next); reloadShows(); }} onDeleted={() => { setToolsOpened(false); setSelected(null); reloadShows(); }} />
      <ShowForm opened={formOpened} initial={editing} options={options} me={me} reloadOptions={reloadOptions} onClose={() => setFormOpened(false)} onSaved={() => { setFormOpened(false); setSelected(null); reloadShows(); }} />
    </main>;
  }

  return <main className="shell">
    <header className="app-header">
      <div><div className="brand">T·IMPRO</div><h1>Мои афиши</h1>{isPreview && <Badge mt={8} color="gray" variant="light">Демо-данные · API отключён</Badge>}</div>
      <div className="header-actions">
        <button
          className={`header-action${teamFilter || yearFilter ? " is-active" : ""}`}
          onClick={() => { telegramHaptic("selection"); setFiltersOpened((opened) => !opened); }}
          aria-label={`Фильтры${[teamFilter, yearFilter].filter(Boolean).length ? `: выбрано ${[teamFilter, yearFilter].filter(Boolean).length}` : ""}`}
          aria-expanded={filtersOpened}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
          {(teamFilter || yearFilter) && <span className="filter-indicator" />}
        </button>
        <button className="header-action" onClick={() => { telegramHaptic("selection"); setManagementOpened(true); }} aria-label="Открыть настройки">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" />
            <path d="M19.4 13.5a7.8 7.8 0 0 0 0-3l1.7-1.3-2-3.4-2 .8a8 8 0 0 0-2.6-1.5L14.2 3h-4.4l-.3 2.1a8 8 0 0 0-2.6 1.5l-2-.8-2 3.4 1.7 1.3a7.8 7.8 0 0 0 0 3l-1.7 1.3 2 3.4 2-.8a8 8 0 0 0 2.6 1.5l.3 2.1h4.4l.3-2.1a8 8 0 0 0 2.6-1.5l2 .8 2-3.4-1.7-1.3Z" />
          </svg>
        </button>
      </div>
    </header>
    <Tabs value={status} onChange={(value) => setStatus(value as "upcoming" | "past")} className="tabs" variant="pills">
      <Tabs.List grow><Tabs.Tab value="upcoming">Будущие</Tabs.Tab><Tabs.Tab value="past">Прошедшие</Tabs.Tab></Tabs.List>
    </Tabs>
    <Collapse expanded={filtersOpened}>
      <Group className="filters-panel" gap="xs" grow>
        <Select clearable searchable placeholder="Все команды" aria-label="Фильтр по команде" value={teamFilter} onChange={setTeamFilter} data={options.teams.map((team) => team.name)} />
        <Select clearable placeholder="Все годы" aria-label="Фильтр по году" value={yearFilter} onChange={setYearFilter} data={Array.from({ length: new Date().getFullYear() - 2019 + 3 }, (_, index) => String(new Date().getFullYear() + 3 - index))} />
      </Group>
    </Collapse>
    {loading && <Stack gap="sm" aria-label="Загружаем афиши"><Skeleton height={184} radius="md" /><Skeleton height={184} radius="md" /></Stack>}
    {error && <Alert color="red" title="Не удалось открыть панель">{error}</Alert>}
    {!loading && !error && shows.length === 0 && <Paper className="state"><Title order={3}>Здесь пока пусто</Title><Text>{status === "upcoming" ? "Создай первую афишу прямо здесь или проверь прошедшие события." : "Прошедших афиш пока нет."}</Text></Paper>}
    <section className="show-list">
      {shows.map((show) => {
        const fill = Math.min(100, Math.round(show.occupiedSeats / Math.max(1, show.maxSeats) * 100));
        return <Paper component="button" className="show-card" key={show.id} onClick={() => { telegramHaptic("selection"); void openShow(show); }}>
          <div className="card-top"><Badge color="gray" variant="light">{show.showDateLabel}</Badge><span className="arrow">→</span></div>
          <Title order={2}>{show.title}</Title><Text>{show.teamName}</Text><Text className="muted">{show.location} · {show.city}</Text>
          <div className="capacity-head"><span>Заполнено</span><strong>{show.occupiedSeats} / {show.maxSeats}</strong></div>
          <Progress value={fill} color="gray" mt={8} />
        </Paper>;
      })}
    </section>
    {showsHasMore && <Button fullWidth mt="md" variant="default" loading={loading} onClick={() => reloadShows(showsNextOffset, true)}>Показать ещё</Button>}
    <Button className="primary" fullWidth onClick={() => { telegramHaptic("light"); setEditing(null); setFormOpened(true); }}>＋ Создать афишу</Button>
    <ShowForm opened={formOpened} initial={editing} options={options} me={me} reloadOptions={reloadOptions} onClose={() => setFormOpened(false)} onSaved={() => { setFormOpened(false); reloadShows(); }} />
    <ManagementModal opened={managementOpened} onClose={() => setManagementOpened(false)} me={me} options={options} reload={reloadOptions} />
  </main>;
}

function ShowToolsModal({ mode, opened, onClose, show, registrationUrl, demo, onChanged, onDeleted }: {
  mode: "all" | "chat"; opened: boolean; onClose: () => void; show: Show; registrationUrl: string; demo: boolean; onChanged: (show: Show) => void; onDeleted: () => void;
}) {
  const cloneDefault = React.useMemo(() => {
    const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  }, []);
  const [cloneDate, setCloneDate] = React.useState(cloneDefault);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [cancelConfirm, setCancelConfirm] = React.useState(false);
  const [deleteConfirm, setDeleteConfirm] = React.useState(false);
  const [remindConfirm, setRemindConfirm] = React.useState(false);
  const [chatTarget, setChatTarget] = React.useState("");
  const [chatNameMode, setChatNameMode] = React.useState<"short" | "full">(show.registrationChatNameMode ?? "short");
  const [tasks, setTasks] = React.useState<{ key: string; label: string; count: number }[]>([]);

  React.useEffect(() => {
    if (!opened || demo) return;
    api<{ items: { key: string; label: string; count: number }[] }>(`/api/miniapp/shows/${show.id}/tasks`).then(({ items }) => setTasks(items)).catch(() => setTasks([]));
  }, [demo, opened, show.id]);

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

  async function restoreShow() {
    setBusy("restore");
    try {
      if (!demo) await api(`/api/miniapp/shows/${show.id}/restore`, { method: "POST" });
      onChanged({ ...show, isActive: true }); onClose();
      notifications.show({ color: "green", title: "Афиша восстановлена", message: "Запись снова доступна" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось восстановить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function deleteShow() {
    setBusy("delete");
    try {
      if (!demo) await api(`/api/miniapp/shows/${show.id}`, { method: "DELETE" });
      setDeleteConfirm(false); onDeleted();
      notifications.show({ color: "green", title: "Афиша удалена", message: "Связанные данные удалены" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось удалить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function saveRegistrationChat() {
    setBusy("chat");
    try {
      const result = await api<{ id: number; title: string; nameMode: "short" | "full" }>(`/api/miniapp/shows/${show.id}/registration-chat`, { method: "PUT", body: JSON.stringify({ target: chatTarget, nameMode: chatNameMode }) });
      onChanged({ ...show, registrationChatId: result.id, registrationChatTitle: result.title, registrationChatNameMode: result.nameMode });
      setChatTarget(""); notifications.show({ color: "green", title: "Рабочий чат подключён", message: result.title });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось подключить чат", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function clearRegistrationChat() {
    setBusy("chat");
    try {
      await api(`/api/miniapp/shows/${show.id}/registration-chat`, { method: "DELETE" });
      onChanged({ ...show, registrationChatId: null, registrationChatTitle: null });
      notifications.show({ color: "green", title: "Рабочий чат отключён", message: "Уведомления о записях больше не отправляются" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось отключить чат", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function remindViewers() {
    setBusy("remind");
    try {
      const result = await api<{ sent: number; failed: number }>(`/api/miniapp/shows/${show.id}/remind`, { method: "POST" });
      setRemindConfirm(false); notifications.show({ color: result.failed ? "yellow" : "green", title: "Напоминания отправлены", message: `Доставлено: ${result.sent} · ошибок: ${result.failed}` });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось отправить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function confirmManualNotifications() {
    setBusy("manual-confirm");
    try {
      const result = await api<{ confirmed: number }>(`/api/miniapp/shows/${show.id}/manual-notifications/confirm`, { method: "POST" });
      setTasks((current) => current.filter((item) => item.key !== "manual_notifications"));
      notifications.show({ color: "green", title: "Отмечено", message: `Уведомлены вручную: ${result.confirmed}` });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  return <Modal opened={opened} onClose={onClose} title={mode === "chat" ? "Чат записей" : "Управление афишей"} fullScreen>
    <Stack>
      {mode === "all" && <><Paper className="resource-form"><Stack><Group justify="space-between"><Title order={3}>Задачи</Title><Badge variant="light">{tasks.length}</Badge></Group>{tasks.length ? tasks.map((task) => <Group key={task.key} justify="space-between"><Text>{task.label}</Text><Badge>{task.count}</Badge></Group>) : <Text c="dimmed">Срочных действий нет</Text>}{tasks.some((item) => item.key === "manual_notifications") && <Button variant="light" loading={busy === "manual-confirm"} onClick={() => void confirmManualNotifications()}>Отметить ручных зрителей уведомлёнными</Button>}</Stack></Paper>
      <Paper className="resource-form"><Stack><div><Title order={3}>Запись зрителей</Title><Text size="sm" c="dimmed">Эта ссылка открывает публичного бота сразу на записи на выбранное шоу. Зритель укажет имя и количество гостей, а его запись появится в списке зрителей.</Text><Text size="sm" c="dimmed" mt={6}>QR-код содержит ту же ссылку. Его можно разместить на картинке, печатной афише или показать со сцены — зритель отсканирует код камерой телефона.</Text></div><Text size="sm" style={{ wordBreak: "break-all" }}>{registrationUrl}</Text><Group grow><Button variant="light" onClick={() => void copyLink()}>Скопировать ссылку</Button><Button loading={busy === "qr"} onClick={() => void downloadQr()}>Скачать QR-код</Button></Group></Stack></Paper></>}
      <Paper className="resource-form"><Stack><Title order={3}>Рабочий чат записей</Title>{show.registrationChatId ? <><Text>Подключён: {show.registrationChatTitle || show.registrationChatId}</Text><Button color="red" variant="light" loading={busy === "chat"} onClick={() => void clearRegistrationChat()}>Отключить чат</Button></> : <><Text size="sm" c="dimmed">Добавь админ-бота в канал с правом публикации и укажи @username или ID −100…</Text><TextInput label="Канал или чат" placeholder="@registrations_chat" value={chatTarget} onChange={(event) => setChatTarget(event.currentTarget.value)} /><Select label="Формат имени" value={chatNameMode} onChange={(value) => setChatNameMode((value as "short" | "full") ?? "short")} data={[{ value: "short", label: "Короткое имя" }, { value: "full", label: "Полное имя" }]} /><Button disabled={!chatTarget.trim()} loading={busy === "chat"} onClick={() => void saveRegistrationChat()}>Проверить и подключить</Button></>}</Stack></Paper>
      {mode === "all" && <>
      {show.isActive && <Button variant="light" loading={busy === "remind"} onClick={() => setRemindConfirm(true)}>Отправить напоминание зрителям</Button>}
      <Paper className="resource-form"><Stack><Title order={3}>Создать похожую афишу</Title><TextInput type="datetime-local" label="Дата и время новой афиши" value={cloneDate} onChange={(event) => setCloneDate(event.currentTarget.value)} /><Button loading={busy === "clone"} onClick={() => void clone()}>Создать копию</Button></Stack></Paper>
      {show.isActive && <Paper className="resource-form"><Stack><Title order={3}>Опасная зона</Title><Text size="sm" c="dimmed">Запись будет закрыта. Если афиша публиковалась, в канал уйдёт сообщение об отмене, а записавшиеся получат уведомление.</Text><Button color="red" variant="light" onClick={() => setCancelConfirm(true)}>Отменить афишу</Button></Stack></Paper>}
      {!show.isActive && <Paper className="resource-form"><Stack><Title order={3}>Отменённая афиша</Title><Button loading={busy === "restore"} onClick={() => void restoreShow()}>Восстановить афишу</Button><Button color="red" variant="light" onClick={() => setDeleteConfirm(true)}>Удалить навсегда</Button></Stack></Paper>}
      </>}
    </Stack>
    <Modal opened={cancelConfirm} onClose={() => setCancelConfirm(false)} title="Точно отменить афишу?" centered><Text>Действие закроет новые записи и отправит уведомления зрителям.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setCancelConfirm(false)}>Не отменять</Button><Button color="red" loading={busy === "cancel"} onClick={() => void cancelShow()}>Да, отменить</Button></Group></Modal>
    <Modal opened={deleteConfirm} onClose={() => setDeleteConfirm(false)} title="Удалить афишу навсегда?" centered><Text>Будут удалены записи, отзывы и история анонсов. Это действие нельзя отменить.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setDeleteConfirm(false)}>Не удалять</Button><Button color="red" loading={busy === "delete"} onClick={() => void deleteShow()}>Удалить навсегда</Button></Group></Modal>
    <Modal opened={remindConfirm} onClose={() => setRemindConfirm(false)} title="Отправить напоминания?" centered><Text>Сообщение будет отправлено всем записанным зрителям от публичного бота.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setRemindConfirm(false)}>Отмена</Button><Button loading={busy === "remind"} onClick={() => void remindViewers()}>Отправить</Button></Group></Modal>
  </Modal>;
}

function MiniAppRoot() {
  const telegram = window.Telegram?.WebApp;
  const [colorScheme, setColorScheme] = React.useState<"light" | "dark">(telegram?.colorScheme ?? "dark");

  React.useEffect(() => {
    const syncTheme = () => {
      const next = telegram?.colorScheme ?? "dark";
      const background = next === "light" ? "#fafafa" : "#0f0f0f";
      setColorScheme(next);
      document.documentElement.dataset.theme = next;
      telegram?.setHeaderColor(background);
      telegram?.setBackgroundColor(background);
      telegram?.setBottomBarColor?.(background);
    };
    if (telegram?.initData) document.documentElement.dataset.telegram = "true";
    syncTheme();
    telegram?.onEvent("themeChanged", syncTheme);
    telegram?.ready();
    telegram?.expand();
    return () => telegram?.offEvent("themeChanged", syncTheme);
  }, [telegram]);

  return <MantineProvider theme={theme} forceColorScheme={colorScheme}><DatesProvider settings={{ locale: "ru", firstDayOfWeek: 1, weekendDays: [0, 6] }}><Notifications /><App /></DatesProvider></MantineProvider>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MiniAppRoot />
  </React.StrictMode>,
);
