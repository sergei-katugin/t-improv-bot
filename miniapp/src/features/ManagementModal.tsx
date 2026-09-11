import React from "react";
import { Button, Group, Modal, Paper, Stack, Switch, Tabs, Text, TextInput, Title } from "@mantine/core";
import { BottomActionBar, RootNavigation } from "../components/BottomActionBar";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { api } from "../lib/api";
import { showNotification } from "../lib/notifications";
import { telegramConfirm } from "../lib/telegram";
import { useAppResume } from "../hooks/useAppResume";
import type { AccessUser, AuditItem, Me, Options, ThemePreference } from "../types";
import { invalidTelegramUsername } from "../lib/validation";
import { AccessModal, AuditLogModal } from "./ManagementAccessModals";
import { TeamsSheet, VenuesSheet } from "./CatalogSheets";
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
  function closeTeams() {
    if (teamEditorOpened) {
      setTeamEditorOpened(false); setTeamId(null); setTeamName(""); setMembers("");
      return;
    }
    setSettingsTab(null);
  }
  function editVenue(venue: Options["venues"][number]) {
    setVenueId(venue.id); setVenueName(venue.name); setVenueCity(venue.city);
    setVenueUrl(venue.mapsUrl ?? ""); setVenueSeats(venue.defaultSeats); setVenueEditorOpened(true);
  }
  function closeVenues() {
    if (venueEditorOpened) {
      setVenueEditorOpened(false); setVenueId(null); setVenueName(""); setVenueCity("Лимасол"); setVenueUrl(""); setVenueSeats(50);
      return;
    }
    setSettingsTab(null);
  }
  function closeChannels() {
    if (channelEditorOpened) {
      setChannelEditorOpened(false); setChannel("");
      return;
    }
    setSettingsTab(null);
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
    <>
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
    {settingsTab !== null && settingsTab !== "teams" && settingsTab !== "venues" && settingsTab !== "channels" && settingsTab !== "access" && <>
      <button type="button" className="settings-section-back" onClick={() => setSettingsTab(null)}>‹ Все настройки</button>
      <div className="page-heading settings-section-heading"><div className="eyebrow">Настройки</div><Title order={1}>{settingsTitle}</Title></div>
      <Tabs value={settingsTab} className="settings-tabs" variant="pills">
      <Tabs.Panel value="appearance" pt="lg"><Stack>
        <AppearanceSettings value={themePreference} onChange={onThemePreferenceChange} onReset={onResetLocalData} />
      </Stack></Tabs.Panel>
      </Tabs>
    </>}
    </>
    <TeamsSheet opened={settingsTab === "teams"} editorOpened={teamEditorOpened} id={teamId} name={teamName} members={members} invalidMember={invalidTeamMember} saving={saving} teams={options.teams} onClose={closeTeams} onName={setTeamName} onMembers={setMembers} onEdit={editTeam} onDelete={(team) => void requestResourceDelete({ kind: "team", id: team.id, name: team.name })} onAdd={() => { setTeamId(null); setTeamName(""); setMembers(""); setTeamEditorOpened(true); }} onSave={() => void saveTeam()} />
    <VenuesSheet opened={settingsTab === "venues"} editorOpened={venueEditorOpened} id={venueId} name={venueName} city={venueCity} url={venueUrl} seats={venueSeats} saving={saving} venues={options.venues} onClose={closeVenues} onName={setVenueName} onCity={setVenueCity} onUrl={setVenueUrl} onSeats={setVenueSeats} onEdit={editVenue} onDelete={(venue) => void requestResourceDelete({ kind: "venue", id: venue.id, name: venue.name })} onAdd={() => { setVenueId(null); setVenueName(""); setVenueCity("Лимасол"); setVenueUrl(""); setVenueSeats(50); setVenueEditorOpened(true); }} onSave={() => void saveVenue()} />
    <Modal
      opened={settingsTab === "channels"}
      onClose={closeChannels}
      title={channelEditorOpened ? "Новый рекламный канал" : "Каналы для анонсов"}
      size={620}
      xOffset={0}
      yOffset={0}
      transitionProps={{ transition: "slide-up", duration: 240, timingFunction: "ease-out" }}
      closeButtonProps={{ "aria-label": channelEditorOpened ? "Закрыть добавление канала" : "Закрыть каналы" }}
      classNames={{ inner: "show-form-sheet-inner", content: "channels-sheet", close: "show-form-close" }}
    >
      {channelEditorOpened ? <Stack>
        <TextInput label="Telegram-ник канала" placeholder="@afisha_cyprus" value={channel} onChange={(event) => setChannel(event.currentTarget.value)} autoFocus />
        <BottomActionBar inline><Button className="primary" fullWidth disabled={!channel.trim()} loading={saving} onClick={() => perform(() => api("/api/miniapp/ad-channels", { method: "POST", body: JSON.stringify({ username: channel }) }), "Канал добавлен").then((saved) => { if (saved) { setChannelEditorOpened(false); setChannel(""); } })}>Добавить канал</Button></BottomActionBar>
      </Stack> : <Stack>
        {options.adChannels.map((item) => <Paper className="resource-card" key={item.id}><Group justify="space-between"><div><Text fw={750}>{item.username}</Text><Text size="sm" c="dimmed">{item.isActive ? "Активен" : "Отключён"}</Text></div><Group gap="xs"><Switch aria-label={`Активность канала ${item.username}`} checked={item.isActive} onChange={() => perform(() => api(`/api/miniapp/ad-channels/${item.id}/toggle`, { method: "PATCH" }), "Канал обновлён")} /><Button size="xs" color="red" variant="subtle" onClick={() => void requestResourceDelete({ kind: "channel", id: item.id, name: item.username })}>Удалить</Button></Group></Group></Paper>)}
        {!options.adChannels.length && <Text c="dimmed">Каналов пока нет.</Text>}
        <BottomActionBar inline><Button className="primary" fullWidth onClick={() => setChannelEditorOpened(true)}>＋ Добавить канал</Button></BottomActionBar>
      </Stack>}
    </Modal>
    <AccessModal opened={settingsTab === "access"} onClose={() => setSettingsTab(null)} users={accessUsers} loading={accessLoading} inviteUrl={inviteUrl} saving={saving} onInvite={() => void createInvite()} onCopy={() => void copyInvite()} onAudit={() => { setAuditOpened(true); void loadAudit(); }} onRevoke={setRevokeUser} />
    <AuditLogModal opened={auditOpened} onClose={() => setAuditOpened(false)} items={auditItems} loading={auditLoading} error={auditError} onReload={() => void loadAudit()} />
    <Modal opened={revokeUser !== null} onClose={() => setRevokeUser(null)} title="Отозвать доступ?" centered><Text>Пользователь {revokeUser?.username ? `@${revokeUser.username}` : revokeUser?.firstName} больше не сможет открывать Mini App и управлять афишами.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setRevokeUser(null)}>Отмена</Button><Button color="red" loading={saving} onClick={() => void confirmRevoke()}>Отозвать</Button></Group></Modal>
  </Modal>;
}
