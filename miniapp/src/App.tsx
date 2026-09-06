import React from "react";
import {
  Alert, Anchor, Autocomplete, Badge, Button, Collapse, FileInput, Group, Loader, MantineProvider, Modal, NumberInput,
  Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text,
  Textarea, TextInput, Title,
} from "@mantine/core";
import { DateTimePicker, DatesProvider } from "@mantine/dates";
import { Notifications, notifications } from "@mantine/notifications";
import "dayjs/locale/ru";
import { BottomActionBar, RootNavigation } from "./components/BottomActionBar";
import { ShowNavigation } from "./components/ShowNavigation";
import { AnalyticsModal } from "./components/AnalyticsModal";
import { ShowForm } from "./features/ShowForm";
import { ManagementModal } from "./features/ManagementModal";
import { AttendeesModal } from "./features/AttendeesModal";
import { AnnouncementModal } from "./features/AnnouncementModal";
import { ShowToolsModal } from "./features/ShowToolsModal";
import { AppSettingsModal } from "./features/AppSettingsModal";
import { ShowCard } from "./components/ShowCard";
import { ShowDetails } from "./components/ShowDetails";
import { ShowsHeader } from "./components/ShowsHeader";
import { ShowStepper } from "./components/ShowStepper";
import { MiniAppOnboarding } from "./components/MiniAppOnboarding";
import { AttentionCenter, type AttentionItem } from "./components/AttentionCenter";
import { api, authenticatedBlob } from "./lib/api";
import { telegramConfirm, telegramHaptic } from "./lib/telegram";
import { useAppTheme } from "./hooks/useAppTheme";
import { useAppResume } from "./hooks/useAppResume";
import { theme } from "./theme";
import type { AccessUser, Attendees, AuditItem, Me, Options, Promotion, RegistrationChatOption, Show, ShowFormValue, ThemePreference } from "./types";

const previewShows: Show[] = [
  { id: 1, title: "Истории на ночь", teamName: "T·IMPRO", showDateLabel: "5 сентября, 20:00", location: "Ravens Music Hall", city: "Лимасол", isActive: true, maxSeats: 50, occupiedSeats: 34, registrarUsername: "sergey", hasPublished: true },
  { id: 2, title: "Маэстро", teamName: "Импровизаторы Кипра", showDateLabel: "12 сентября, 19:30", location: "Yurts in Cyprus", city: "Пафос", isActive: true, maxSeats: 40, occupiedSeats: 18, registrarUsername: "anna_impro", hasPublished: false },
];



function App({ themePreference, onThemePreferenceChange, onResetLocalData }: { themePreference: ThemePreference; onThemePreferenceChange: (preference: ThemePreference) => void; onResetLocalData: () => void }) {
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
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [attention, setAttention] = React.useState<AttentionItem[]>([]);
  const [options, setOptions] = React.useState<Options>({ teams: [], venues: [], adChannels: [] });
  const [me, setMe] = React.useState<Me | null>(isPreview ? { id: 1, firstName: "Sergey", username: "sergey", role: "admin" } : null);
  const [formOpened, setFormOpened] = React.useState(false);
  const [managementOpened, setManagementOpened] = React.useState(false);
  const [settingsOpened, setSettingsOpened] = React.useState(false);
  const [attendeesOpened, setAttendeesOpened] = React.useState(false);
  const [announcementOpened, setAnnouncementOpened] = React.useState(false);
  const [analyticsOpened, setAnalyticsOpened] = React.useState(false);
  const [toolsOpened, setToolsOpened] = React.useState(false);
  const [toolsMode, setToolsMode] = React.useState<"all" | "chat" | "registration">("all");
  const [descriptionOpened, setDescriptionOpened] = React.useState(false);
  const [editing, setEditing] = React.useState<Show | null>(null);
  const managementBackRef = React.useRef<(() => boolean) | null>(null);
  const attendeesBackRef = React.useRef<(() => boolean) | null>(null);
  const toolsBackRef = React.useRef<(() => boolean) | null>(null);
  const showsRequestRef = React.useRef(0);

  const hasBackTarget = Boolean(selected || formOpened || managementOpened || settingsOpened || attendeesOpened || announcementOpened || analyticsOpened || toolsOpened);

  React.useEffect(() => {
    const title = formOpened ? (editing ? "Редактирование афиши" : "Новая афиша")
      : managementOpened ? "Администрирование"
      : settingsOpened ? "Настройки"
      : attendeesOpened ? "Зрители"
      : announcementOpened ? "Анонс"
      : analyticsOpened ? "Аналитика"
      : toolsOpened ? `${selected?.isPast ? "Настройки" : "Действия"} · ${selected?.title ?? "Шоу"}`
      : selected?.title ?? "Мои афиши";
    document.title = title;
  }, [analyticsOpened, announcementOpened, attendeesOpened, editing, formOpened, managementOpened, selected, settingsOpened, toolsOpened]);

  React.useEffect(() => {
    const backButton = window.Telegram?.WebApp.BackButton;
    if (!backButton) return;
    const goBack = () => {
      telegramHaptic("light");
      if (toolsOpened) {
        if (!toolsBackRef.current?.()) setToolsOpened(false);
      }
      else if (analyticsOpened) setAnalyticsOpened(false);
      else if (announcementOpened) setAnnouncementOpened(false);
      else if (attendeesOpened) {
        if (!attendeesBackRef.current?.()) setAttendeesOpened(false);
      }
      else if (formOpened) { setFormOpened(false); setEditing(null); }
      else if (managementOpened) {
        if (!managementBackRef.current?.()) setManagementOpened(false);
      }
      else if (settingsOpened) setSettingsOpened(false);
      else if (selected) setSelected(null);
    };
    backButton.onClick(goBack);
    if (hasBackTarget) backButton.show(); else backButton.hide();
    return () => backButton.offClick(goBack);
  }, [analyticsOpened, announcementOpened, attendeesOpened, formOpened, hasBackTarget, managementOpened, selected, settingsOpened, toolsOpened]);

  React.useEffect(() => {
    const settingsButton = window.Telegram?.WebApp.SettingsButton;
    if (!settingsButton) return;
    settingsButton.hide();
  }, []);

  React.useEffect(() => {
    if (!isPreview) { api<Options>("/api/miniapp/options").then(setOptions).catch(() => undefined); api<Me>("/api/miniapp/me").then(setMe).catch(() => undefined); }
    else setOptions({ teams: [{ id: 1, name: "T·IMPRO", members: "@sergey, @anna_impro" }, { id: 2, name: "Импровизаторы Кипра", members: null }], venues: [{ id: 1, name: "Ravens Music Hall", city: "Лимасол", mapsUrl: "https://maps.example", defaultSeats: 50 }], adChannels: [{ id: 1, username: "@afisha_cyprus", isActive: true }] });
  }, [isPreview]);

  function reloadShows(offset = 0, append = false) {
    if (isPreview) return;
    const requestId = ++showsRequestRef.current;
    if (append) setLoadingMore(true);
    else {
      setLoading(true);
      setShows([]);
      setShowsHasMore(false);
    }
    setError(null);
    const query = new URLSearchParams({ status, offset: String(offset) });
    if (teamFilter) query.set("team", teamFilter);
    if (yearFilter) query.set("year", yearFilter);
    api<{ items: Show[]; hasMore: boolean; nextOffset: number }>(`/api/miniapp/shows?${query}`)
      .then(({ items, hasMore, nextOffset }) => {
        if (requestId !== showsRequestRef.current) return;
        setShows((current) => append ? [...current, ...items] : items);
        setShowsHasMore(hasMore); setShowsNextOffset(nextOffset);
      })
      .catch((reason: Error) => {
        if (requestId === showsRequestRef.current) setError(reason.message);
      })
      .finally(() => {
        if (requestId !== showsRequestRef.current) return;
        if (append) setLoadingMore(false); else setLoading(false);
      });
  }

  function changeStatus(nextStatus: "upcoming" | "past") {
    if (nextStatus === status) return;
    if (isPreview) {
      setStatus(nextStatus);
      return;
    }
    showsRequestRef.current += 1;
    setShows([]);
    setShowsHasMore(false);
    setLoading(true);
    setLoadingMore(false);
    setStatus(nextStatus);
  }

  async function reloadOptions() {
    if (isPreview) return;
    setOptions(await api<Options>("/api/miniapp/options"));
  }

  const reloadAttention = React.useCallback(() => {
    if (isPreview) return;
    api<{ items: AttentionItem[] }>("/api/miniapp/attention").then(({ items }) => setAttention(items)).catch(() => undefined);
  }, [isPreview]);

  React.useEffect(() => {
    if (isPreview) return;
    setLoading(true);
    setError(null);
    reloadShows();
    reloadAttention();
  }, [status, teamFilter, yearFilter, isPreview, reloadAttention]);

  useAppResume(() => {
    if (isPreview) return;
    void reloadOptions();
    reloadAttention();
    reloadShows();
    if (selected) api<Show>(`/api/miniapp/shows/${selected.id}`).then(setSelected).catch(() => undefined);
  });

  async function openAttention(item: AttentionItem) {
    const show = shows.find((candidate) => candidate.id === item.showId) ?? await api<Show>(`/api/miniapp/shows/${item.showId}`);
    setSelected(show);
    if (item.kind === "announcement") setAnnouncementOpened(true);
    else if (item.kind === "chat") { setToolsMode("chat"); setToolsOpened(true); }
    else { setEditing(show); setFormOpened(true); }
  }

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
    const registrationUrl = selected.registrationUrl ?? `https://t.me/ImprovCypEventBot?start=show_${selected.id}`;
    return <main className="shell">
      <Button className="back" variant="subtle" onClick={() => { telegramHaptic("light"); setSelected(null); }}>← Все афиши</Button>
      <ShowDetails show={selected} descriptionOpened={descriptionOpened} onToggleDescription={() => setDescriptionOpened((opened) => !opened)} onAttendees={() => setAttendeesOpened(true)} onEdit={() => { setEditing(selected); setFormOpened(true); }} onAnnouncement={() => setAnnouncementOpened(true)} onAnalytics={() => setAnalyticsOpened(true)} onRegistration={() => { setToolsMode("registration"); setToolsOpened(true); }} onMore={() => { setToolsMode("all"); setToolsOpened(true); }} />
      <AttendeesModal
        opened={attendeesOpened}
        onClose={() => setAttendeesOpened(false)}
        show={selected}
        demo={isPreview}
        backHandlerRef={attendeesBackRef}
        onEdit={() => { setAttendeesOpened(false); setEditing(selected); setFormOpened(true); }}
        onAnnouncement={() => { setAttendeesOpened(false); setAnnouncementOpened(true); }}
        onAnalytics={() => { setAttendeesOpened(false); setAnalyticsOpened(true); }}
        onRegistration={() => { setAttendeesOpened(false); setToolsMode("registration"); setToolsOpened(true); }}
        onMore={() => { setAttendeesOpened(false); setToolsMode("all"); setToolsOpened(true); }}
      />
      <AnnouncementModal
        opened={announcementOpened}
        onClose={() => setAnnouncementOpened(false)}
        show={selected}
        demo={isPreview}
        onEdit={() => { setAnnouncementOpened(false); setEditing(selected); setFormOpened(true); }}
        onAnalytics={() => { setAnnouncementOpened(false); setAnalyticsOpened(true); }}
        onRegistration={() => { setAnnouncementOpened(false); setToolsMode("registration"); setToolsOpened(true); }}
        onMore={() => { setAnnouncementOpened(false); setToolsMode("all"); setToolsOpened(true); }}
        onPublished={() => setSelected((current) => current ? { ...current, hasPublished: true } : current)}
      />
      <AnalyticsModal opened={analyticsOpened} onClose={() => setAnalyticsOpened(false)} show={selected} demo={isPreview} onEdit={() => { setAnalyticsOpened(false); setEditing(selected); setFormOpened(true); }} onAnnouncement={() => { setAnalyticsOpened(false); setAnnouncementOpened(true); }} onRegistration={() => { setAnalyticsOpened(false); setToolsMode("registration"); setToolsOpened(true); }} onMore={() => { setAnalyticsOpened(false); setToolsMode("all"); setToolsOpened(true); }} />
      <ShowToolsModal mode={toolsMode} opened={toolsOpened} onClose={() => setToolsOpened(false)} show={selected} registrationUrl={registrationUrl} demo={isPreview} backHandlerRef={toolsBackRef} onEdit={() => { setToolsOpened(false); setEditing(selected); setFormOpened(true); }} onAnalytics={() => { setToolsOpened(false); setAnalyticsOpened(true); }} onAnnouncement={() => { setToolsOpened(false); setAnnouncementOpened(true); }} onChanged={(next) => { setSelected(next); reloadShows(); }} onDeleted={() => { setToolsOpened(false); setSelected(null); reloadShows(); }} />
      <ShowForm opened={formOpened} initial={editing} options={options} me={me} reloadOptions={reloadOptions} onClose={() => setFormOpened(false)} onSaved={() => { setFormOpened(false); setSelected(null); reloadShows(); }} />
    </main>;
  }

  return <main className="shell">
    <ShowsHeader status={status} onStatusChange={changeStatus} filtersOpened={filtersOpened} activeFilters={[teamFilter, yearFilter].filter(Boolean).length} onToggleFilters={() => { telegramHaptic("selection"); setFiltersOpened((opened) => !opened); }} />
    <Collapse expanded={filtersOpened}>
      <Group className="filters-panel" gap="xs" grow>
        <Select clearable searchable placeholder="Все команды" aria-label="Фильтр по команде" value={teamFilter} onChange={setTeamFilter} data={options.teams.map((team) => team.name)} />
        <Select clearable placeholder="Все годы" aria-label="Фильтр по году" value={yearFilter} onChange={setYearFilter} data={Array.from({ length: new Date().getFullYear() - 2019 + 3 }, (_, index) => String(new Date().getFullYear() + 3 - index))} />
      </Group>
    </Collapse>
    {status === "upcoming" && <AttentionCenter items={attention} onOpen={(item) => void openAttention(item)} />}
    {loading && <Stack gap="sm" aria-label="Загружаем афиши"><Skeleton height={184} radius="md" /><Skeleton height={184} radius="md" /></Stack>}
    {error && <Alert color="red" title="Не удалось открыть панель">{error}</Alert>}
    {!loading && !error && shows.length === 0 && <Paper className="state"><Title order={3}>Здесь пока пусто</Title><Text>{status === "upcoming" ? "Создай первую афишу прямо здесь или проверь прошедшие события." : "Прошедших афиш пока нет."}</Text></Paper>}
    {!loading && <section className="show-list">
      {shows.map((show) => <ShowCard key={show.id} show={show} onClick={() => { telegramHaptic("selection"); void openShow(show); }} onCopyLink={() => { const url = show.registrationUrl ?? `https://t.me/ImprovCypEventBot?start=show_${show.id}`; void navigator.clipboard.writeText(url).then(() => notifications.show({ color: "green", title: "Ссылка скопирована", message: show.title })).catch(() => notifications.show({ color: "red", title: "Не удалось скопировать", message: url })); }} onAnnouncement={() => { setSelected(show); setAnnouncementOpened(true); }} />)}
    </section>}
    {showsHasMore && <Button fullWidth mt="md" variant="default" loading={loadingMore} onClick={() => reloadShows(showsNextOffset, true)}>Показать ещё</Button>}
    <RootNavigation onShows={() => setSelected(null)} onCreate={() => { telegramHaptic("light"); setEditing(null); setFormOpened(true); }} onAdministration={() => { telegramHaptic("selection"); setManagementOpened(true); }} onSettings={() => { telegramHaptic("selection"); setSettingsOpened(true); }} />
    <ShowForm opened={formOpened} initial={editing} options={options} me={me} reloadOptions={reloadOptions} onClose={() => setFormOpened(false)} onSaved={() => { setFormOpened(false); reloadShows(); }} />
    <ManagementModal opened={managementOpened} onClose={() => setManagementOpened(false)} onCreate={() => { setManagementOpened(false); setEditing(null); setFormOpened(true); }} onSettings={() => { setManagementOpened(false); setSettingsOpened(true); }} me={me} options={options} reload={reloadOptions} themePreference={themePreference} onThemePreferenceChange={onThemePreferenceChange} onResetLocalData={onResetLocalData} backHandlerRef={managementBackRef} />
    <AppSettingsModal opened={settingsOpened} onClose={() => setSettingsOpened(false)} onCreate={() => { setSettingsOpened(false); setEditing(null); setFormOpened(true); }} onAdministration={() => { setSettingsOpened(false); setManagementOpened(true); }} value={themePreference} onChange={onThemePreferenceChange} onReset={onResetLocalData} />
  </main>;
}

export function AppRoot() {
  const { colorScheme, preference, changePreference } = useAppTheme();
  const onboardingKey = "miniapp-onboarding-v1";
  const [onboardingOpened, setOnboardingOpened] = React.useState(() => localStorage.getItem(onboardingKey) !== "done");
  const finishOnboarding = React.useCallback(() => {
    localStorage.setItem(onboardingKey, "done");
    setOnboardingOpened(false);
  }, []);
  const resetLocalData = React.useCallback(() => {
    localStorage.clear();
    sessionStorage.clear();
    document.cookie.split(";").forEach((cookie) => {
      const name = cookie.split("=", 1)[0]?.trim();
      if (name) document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax`;
    });
    changePreference("system");
    setOnboardingOpened(true);
  }, [changePreference]);
  return <MantineProvider theme={theme} forceColorScheme={colorScheme}><DatesProvider settings={{ locale: "ru", firstDayOfWeek: 1, weekendDays: [0, 6] }}><Notifications /><App themePreference={preference} onThemePreferenceChange={changePreference} onResetLocalData={resetLocalData} /><MiniAppOnboarding opened={onboardingOpened} onFinish={finishOnboarding} /></DatesProvider></MantineProvider>;
}
