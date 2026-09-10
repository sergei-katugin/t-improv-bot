import React from "react";
import { Alert, Anchor, Autocomplete, Badge, Button, Collapse, FileInput, Group, Loader, Modal, NumberInput, Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text, Textarea, TextInput, Title } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { BottomActionBar, RootNavigation } from "../components/BottomActionBar";
import { ShowNavigation } from "../components/ShowNavigation";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { ShowStepper } from "../components/ShowStepper";
import { api, authenticatedBlob } from "../lib/api";
import { showNotification } from "../lib/notifications";
import { telegramConfirm, telegramHaptic } from "../lib/telegram";
import { useAppResume } from "../hooks/useAppResume";
import type { AccessUser, Attendees, AuditItem, Me, Options, Promotion, RegistrationChatOption, Show, ShowFormValue, ThemePreference } from "../types";
import { invalidTelegramUsername } from "../lib/validation";

export function ManagementModal({ opened, onClose, onCreate, onSettings, me, options, reload, themePreference, onThemePreferenceChange, onResetLocalData, backHandlerRef }: {
  opened: boolean; onClose: () => void; me: Me | null; options: Options; reload: () => Promise<void>;
  onCreate?: () => void; onSettings?: () => void;
  themePreference: ThemePreference; onThemePreferenceChange: (preference: ThemePreference) => void;
  onResetLocalData: () => void;
  backHandlerRef?: React.MutableRefObject<(() => boolean) | null>;
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
  const [settingsTab, setSettingsTab] = React.useState<"appearance" | "teams" | "venues" | "channels" | "access" | null>(null);
  const invalidTeamMember = invalidTelegramUsername(members);
  const settingsTitle = settingsTab ? {
    appearance: "Оформление",
    teams: "Команды",
    venues: "Площадки",
    channels: "Каналы для анонсов",
    access: "Доступ и журнал",
  }[settingsTab] : "";

  const loadAccess = React.useCallback(async () => {
    if (me?.role !== "admin") return;
    setAccessLoading(true);
    try {
      if (import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1") {
        setAccessUsers([{ id: 1, telegramId: 416607535, username: "sergey", firstName: "Sergey", lastName: null, role: "admin", isCurrent: true, isProtected: true }, { id: 2, telegramId: 123, username: "anna_impro", firstName: "Анна", lastName: null, role: "organizer", isCurrent: false, isProtected: false }]);
      } else setAccessUsers((await api<{ items: AccessUser[] }>("/api/miniapp/access/users")).items);
    } catch (reason) { showNotification({ color: "red", title: "Не удалось загрузить доступы", message: (reason as Error).message }); }
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
    } catch (reason) { const message = (reason as Error).message; setAuditError(message); showNotification({ color: "red", title: "Не удалось загрузить журнал", message }); }
    finally { setAuditLoading(false); }
  }, [me?.role]);

  async function perform(action: () => Promise<unknown>, success: string) {
    setSaving(true);
    try {
      await action(); await reload();
      showNotification({ color: "gray", title: success, message: "Справочник обновлён" });
      return true;
    } catch (reason) {
      showNotification({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message });
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

  async function saveTeam() {
    if (!teamName.trim() || invalidTeamMember) return;
    const saved = await perform(
      () => api(teamId ? `/api/miniapp/teams/${teamId}` : "/api/miniapp/teams", {
        method: teamId ? "PATCH" : "POST",
        body: JSON.stringify({ name: teamName.trim(), members }),
      }),
      teamId ? "Команда обновлена" : "Команда создана",
    );
    if (saved) {
      setTeamEditorOpened(false); setTeamId(null); setTeamName(""); setMembers("");
    }
  }

  async function saveVenue() {
    if (!venueName.trim() || !venueCity.trim()) return;
    const saved = await perform(
      () => api(venueId ? `/api/miniapp/venues/${venueId}` : "/api/miniapp/venues", {
        method: venueId ? "PATCH" : "POST",
        body: JSON.stringify({
          name: venueName.trim(), city: venueCity.trim(), mapsUrl: venueUrl.trim(), defaultSeats: venueSeats,
        }),
      }),
      venueId ? "Площадка обновлена" : "Площадка добавлена",
    );
    if (saved) {
      setVenueEditorOpened(false); setVenueId(null); setVenueName(""); setVenueCity("Лимасол"); setVenueUrl(""); setVenueSeats(50);
    }
  }

  async function requestResourceDelete(target: { kind: "team" | "venue" | "channel"; id: number; name: string }) {
    const confirmed = await telegramConfirm(`Удалить «${target.name}»? Это действие нельзя отменить.`);
    if (!confirmed) return;
    const paths = { team: "teams", venue: "venues", channel: "ad-channels" };
    await perform(() => api(`/api/miniapp/${paths[target.kind]}/${target.id}`, { method: "DELETE" }), "Удалено");
  }

  async function createInvite() {
    setSaving(true);
    try {
      const preview = import.meta.env.DEV && new URLSearchParams(location.search).get("preview") === "1";
      const result = preview ? { url: "https://t.me/ImprovCypEventBot?start=inv_demo", ttlHours: 24 } : await api<{ url: string; ttlHours: number }>("/api/miniapp/access/invites", { method: "POST", body: JSON.stringify({ role: "organizer" }) });
      setInviteUrl(result.url);
      showNotification({ color: "green", title: "Ссылка создана", message: `Одноразовая, действует ${result.ttlHours} ч.` });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось создать приглашение", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  async function copyInvite() {
    if (!inviteUrl) return;
    try { await navigator.clipboard.writeText(inviteUrl); showNotification({ color: "green", title: "Скопировано", message: "Отправьте ссылку будущему организатору" }); }
    catch { showNotification({ color: "red", title: "Не удалось скопировать", message: inviteUrl }); }
  }

  async function confirmRevoke() {
    if (!revokeUser) return;
    setSaving(true);
    try {
      await api(`/api/miniapp/access/users/${revokeUser.id}`, { method: "PATCH", body: JSON.stringify({ role: "user" }) });
      setRevokeUser(null); await loadAccess();
      showNotification({ color: "green", title: "Доступ отозван", message: "Пользователь больше не может управлять афишами" });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось изменить доступ", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }
  useAppResume(() => {
    void reload();
    if (settingsTab === "access") void loadAccess();
    if (auditOpened) void loadAudit();
  }, opened);

  React.useEffect(() => {
    if (!opened) {
      setSettingsTab(null);
      setAuditOpened(false);
      if (backHandlerRef) backHandlerRef.current = null;
      return;
    }
    if (!backHandlerRef) return;
    backHandlerRef.current = () => {
      if (auditOpened) { setAuditOpened(false); return true; }
      if (teamEditorOpened) { setTeamEditorOpened(false); return true; }
      if (venueEditorOpened) { setVenueEditorOpened(false); return true; }
      if (channelEditorOpened) { setChannelEditorOpened(false); return true; }
      if (revokeUser) { setRevokeUser(null); return true; }
      if (settingsTab) { setSettingsTab(null); return true; }
      return false;
    };
    return () => { backHandlerRef.current = null; };
  }, [auditOpened, backHandlerRef, channelEditorOpened, opened, revokeUser, settingsTab, teamEditorOpened, venueEditorOpened]);

  return <Modal opened={opened} onClose={onClose} fullScreen withCloseButton={false}>
    {teamEditorOpened ? <div className="settings-editor-screen">
      <Stack gap="lg">
        <div className="page-heading"><div className="eyebrow">Команды</div><Title order={1}>{teamId ? "Редактировать команду" : "Новая команда"}</Title></div>
        <TextInput label="Название" value={teamName} onChange={(event) => setTeamName(event.currentTarget.value)} autoFocus />
        <Textarea
          label="Telegram-ники участников"
          description="Через запятую или с новой строки. Ник содержит 5–32 латинских символа, цифры или _."
          placeholder="@sergey, @anna_impro"
          value={members}
          error={invalidTeamMember ? `Проверь ник: ${invalidTeamMember}` : undefined}
          onChange={(event) => setMembers(event.currentTarget.value)}
          autosize
          minRows={4}
        />
      </Stack>
      <BottomActionBar><Button className="primary" fullWidth disabled={!teamName.trim() || Boolean(invalidTeamMember)} loading={saving} onClick={() => void saveTeam()}>{teamId ? "Сохранить" : "Добавить команду"}</Button></BottomActionBar>
    </div> : venueEditorOpened ? <div className="settings-editor-screen">
      <Stack gap="lg">
        <div className="page-heading"><div className="eyebrow">Площадки</div><Title order={1}>{venueId ? "Редактировать площадку" : "Новая площадка"}</Title></div>
        <TextInput label="Название" value={venueName} onChange={(event) => setVenueName(event.currentTarget.value)} autoFocus />
        <Autocomplete label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={venueCity} onChange={setVenueCity} />
        <NumberInput min={1} label="Количество мест" value={venueSeats} onChange={(next) => setVenueSeats(typeof next === "number" ? next : 1)} />
        <TextInput type="url" label="Ссылка на карту" description="Необязательно" placeholder="https://maps.google.com/…" value={venueUrl} onChange={(event) => setVenueUrl(event.currentTarget.value)} />
      </Stack>
      <BottomActionBar><Button className="primary" fullWidth disabled={!venueName.trim() || !venueCity.trim()} loading={saving} onClick={() => void saveVenue()}>{venueId ? "Сохранить" : "Добавить площадку"}</Button></BottomActionBar>
    </div> : <>
    {settingsTab === null && <div className="settings-menu">
      <div className="page-heading"><div className="eyebrow">T·IMPRO</div><Title order={1}>Администрирование</Title></div>
      <div className="settings-list">
        <button type="button" onClick={() => setSettingsTab("teams")}><span><b>Команды</b><small>{options.teams.length} в справочнике</small></span><span>›</span></button>
        {me?.role === "admin" && <button type="button" onClick={() => setSettingsTab("venues")}><span><b>Площадки</b><small>{options.venues.length} в справочнике</small></span><span>›</span></button>}
        {me?.role === "admin" && <button type="button" onClick={() => setSettingsTab("channels")}><span><b>Каналы для анонсов</b><small>{options.adChannels.length} подключено</small></span><span>›</span></button>}
        {me?.role === "admin" && <button type="button" onClick={() => setSettingsTab("access")}><span><b>Доступ и журнал</b><small>Организаторы и история действий</small></span><span>›</span></button>}
      </div>
      <RootNavigation active="administration" onShows={onClose} onCreate={onCreate ?? onClose} onAdministration={() => undefined} onSettings={onSettings ?? onClose} />
    </div>}
    {settingsTab !== null && <>
      <button type="button" className="settings-section-back" onClick={() => setSettingsTab(null)}>‹ Все настройки</button>
      <div className="page-heading settings-section-heading"><div className="eyebrow">Настройки</div><Title order={1}>{settingsTitle}</Title></div>
      <Tabs value={settingsTab} className="settings-tabs" variant="pills">
      <Tabs.Panel value="appearance" pt="lg"><Stack>
        <AppearanceSettings value={themePreference} onChange={onThemePreferenceChange} onReset={onResetLocalData} />
      </Stack></Tabs.Panel>
      <Tabs.Panel value="teams" pt="lg"><Stack>
        {options.teams.map((team) => <Paper className="resource-card" key={team.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{team.name}</Text><Text size="sm" c="dimmed">{team.members || "Участники не указаны"}</Text></div><Group gap="xs"><Button size="xs" variant="light" onClick={() => editTeam(team)}>Изменить</Button><Button size="xs" color="red" variant="subtle" onClick={() => void requestResourceDelete({ kind: "team", id: team.id, name: team.name })}>Удалить</Button></Group></Group></Paper>)}
      </Stack></Tabs.Panel>
      <Tabs.Panel value="venues" pt="lg"><Stack>
        {options.venues.map((venue) => <Paper className="resource-card" key={venue.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{venue.name}</Text><Text size="sm" c="dimmed">{venue.city} · {venue.defaultSeats} мест</Text></div><Group gap="xs"><Button size="xs" variant="light" onClick={() => editVenue(venue)}>Изменить</Button><Button size="xs" color="red" variant="subtle" onClick={() => void requestResourceDelete({ kind: "venue", id: venue.id, name: venue.name })}>Удалить</Button></Group></Group></Paper>)}
      </Stack></Tabs.Panel>
      <Tabs.Panel value="channels" pt="lg"><Stack>
        {options.adChannels.map((item) => <Paper className="resource-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.username}</Text><Text size="sm" c="dimmed">{item.isActive ? "Активен" : "Отключён"}</Text></div><Group gap="xs"><Switch checked={item.isActive} onChange={() => perform(() => api(`/api/miniapp/ad-channels/${item.id}/toggle`, { method: "PATCH" }), "Канал обновлён")} /><Button size="xs" color="red" variant="subtle" onClick={() => void requestResourceDelete({ kind: "channel", id: item.id, name: item.username })}>Удалить</Button></Group></Group></Paper>)}
      </Stack></Tabs.Panel>
      <Tabs.Panel value="access" pt="lg"><Stack>
        <Paper className="resource-form"><Stack><Title order={3}>Пригласить организатора</Title><Text size="sm" c="dimmed">Ссылка одноразовая и автоматически истечёт. Новый пользователь сможет управлять только созданными им афишами.</Text>{inviteUrl && <Text size="sm" style={{ wordBreak: "break-all" }}>{inviteUrl}</Text>}</Stack></Paper>
        <Title order={3}>Пользователи с доступом</Title>
        {accessLoading && <Loader size="sm" />}
        {!accessLoading && accessUsers.map((user) => <Paper className="resource-card" key={user.id}><Group justify="space-between" align="flex-start"><div><Group gap="xs"><Text fw={750}>{[user.firstName, user.lastName].filter(Boolean).join(" ") || user.username || user.telegramId}</Text><Badge color={user.role === "admin" ? "yellow" : "gray"}>{user.role === "admin" ? "Администратор" : "Организатор"}</Badge>{user.isCurrent && <Badge color="gray">Вы</Badge>}</Group>{user.username && <Anchor size="sm" href={`https://t.me/${user.username}`} target="_blank">@{user.username}</Anchor>}</div>{!user.isProtected && !user.isCurrent && <Button size="xs" color="red" variant="subtle" onClick={() => setRevokeUser(user)}>Отозвать</Button>}</Group></Paper>)}
        {!accessLoading && !accessUsers.length && <Text c="dimmed">Пользователей с доступом нет.</Text>}
        <Button variant="default" onClick={() => { setAuditOpened(true); void loadAudit(); }}>Журнал действий</Button>
      </Stack></Tabs.Panel>
      </Tabs>
    </>}
    {settingsTab && settingsTab !== "appearance" && <BottomActionBar>{settingsTab === "teams" ? <Button className="primary" fullWidth onClick={() => { setTeamId(null); setTeamName(""); setMembers(""); setTeamEditorOpened(true); }}>＋ Добавить команду</Button> : settingsTab === "venues" ? <Button className="primary" fullWidth onClick={() => { setVenueId(null); setVenueName(""); setVenueCity("Лимасол"); setVenueUrl(""); setVenueSeats(50); setVenueEditorOpened(true); }}>＋ Добавить площадку</Button> : settingsTab === "channels" ? <Button className="primary" fullWidth onClick={() => setChannelEditorOpened(true)}>＋ Добавить канал</Button> : inviteUrl ? <Button className="primary" fullWidth onClick={() => void copyInvite()}>Копировать приглашение</Button> : <Button className="primary" fullWidth loading={saving} onClick={() => void createInvite()}>＋ Пригласить организатора</Button>}</BottomActionBar>}
    </>}
    <Modal opened={channelEditorOpened} onClose={() => setChannelEditorOpened(false)} title="Новый рекламный канал" centered><Stack><TextInput label="Telegram-ник канала" placeholder="@afisha_cyprus" value={channel} onChange={(e) => setChannel(e.currentTarget.value)} /><Button disabled={!channel.trim()} loading={saving} onClick={() => perform(() => api("/api/miniapp/ad-channels", { method: "POST", body: JSON.stringify({ username: channel }) }), "Канал добавлен").then((saved) => { if (saved) { setChannelEditorOpened(false); setChannel(""); } })}>Добавить канал</Button></Stack></Modal>
    <Modal opened={auditOpened} onClose={() => setAuditOpened(false)} title="Журнал действий" fullScreen classNames={{ close: "fullscreen-modal-close" }}><Stack>
        <Group justify="space-between" align="center"><Text size="sm" c="dimmed">Последние 100 административных операций Mini App</Text><Button size="xs" variant="light" loading={auditLoading} onClick={() => void loadAudit()}>Обновить</Button></Group>
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
  </Modal>;
}

export const previewAttendees: Attendees = {
  occupied: 6, maxSeats: 50, arrived: 3, hasMore: false, nextOffset: 100,
  registrations: [
    { id: 1, name: "Анна Смирнова", guests: 1, username: "anna_impro", confirmed: true, checkedInCount: 2, source: "telegram" },
    { id: 2, name: "Михаил Орлов", guests: 0, username: "m_orlov", confirmed: null, checkedInCount: 0, source: "telegram" },
  ],
  manual: [{ id: 11, name: "Елена", contact: "@elena_cy", guests: 1, checkedInCount: 1, source: "manual" }],
  waitlist: [{ id: 21, name: "Олег", username: "oleg_impro", position: 1 }],
};
