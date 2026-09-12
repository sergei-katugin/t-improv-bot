import React from "react";
import { Alert, Anchor, Autocomplete, Badge, Button, Collapse, FileInput, Group, Loader, Modal, NumberInput, Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text, Textarea, TextInput, Title } from "@mantine/core";
import { BottomActionBar, RootNavigation } from "../components/BottomActionBar";
import { ShowNavigation } from "../components/ShowNavigation";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { ShowStepper } from "../components/ShowStepper";
import { AppDateTimePicker } from "../components/AppDateTimePicker";
import { PosterPreviewImage } from "../components/PosterPreviewImage";
import { ShowAutomationSwitches } from "../components/ShowAutomationSwitches";
import { BoldDescription } from "../components/BoldDescription";
import { api, authenticatedBlob } from "../lib/api";
import { showNotification } from "../lib/notifications";
import { telegramConfirm, telegramHaptic } from "../lib/telegram";
import { useAppResume } from "../hooks/useAppResume";
import { clearShowFormDraft, readShowFormDraft, showFormDraftKey, useShowFormDraft } from "../hooks/useShowFormDraft";
import type { AccessUser, Attendees, AuditItem, Me, Options, Promotion, RegistrationChatOption, Show, ShowFormValue, ThemePreference } from "../types";
import { invalidTelegramUsername } from "../lib/validation";

export function newShowForm(): ShowFormValue {
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  return { title: "", titleNewcomer: "", teamName: "", showDateLocal: local, location: "", locationUrl: "", city: "Лимасол", posterText: "", posterTextNewcomer: "", maxSeats: 50, maxGuests: 6, registrarUsername: "", checkinEnabled: false, checkinMode: "named", checkinReportEvery: 10, feedbackEnabled: true };
}

function formFromShow(show: Show): ShowFormValue {
  return {
    title: show.title, titleNewcomer: show.titleNewcomer ?? "", teamName: show.teamName, showDateLocal: show.showDateLocal ?? "",
    location: show.location, locationUrl: show.locationUrl ?? "", city: show.city,
    posterText: show.posterText ?? "", posterTextNewcomer: show.posterTextNewcomer ?? "", maxSeats: show.maxSeats, maxGuests: show.maxGuests ?? 6,
    registrarUsername: show.registrarUsername ? `@${show.registrarUsername}` : "",
    checkinEnabled: show.checkinEnabled ?? false, checkinMode: show.checkinMode ?? "named", checkinReportEvery: show.checkinReportEvery ?? 10, feedbackEnabled: show.feedbackEnabled ?? false,
  };
}

export function ShowForm({ opened, initial, options, me, reloadOptions, onClose, onSaved }: {
  opened: boolean; initial: Show | null; options: Options; me: Me | null;
  reloadOptions: () => Promise<void>; onClose: () => void; onSaved: (id: number) => void;
}) {
  const [value, setValue] = React.useState<ShowFormValue>(newShowForm());
  const [venueId, setVenueId] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [teamModal, setTeamModal] = React.useState(false);
  const [teamDropdownOpened, setTeamDropdownOpened] = React.useState(false);
  const [venueModal, setVenueModal] = React.useState(false);
  const [newTeamName, setNewTeamName] = React.useState("");
  const [newTeamMembers, setNewTeamMembers] = React.useState("");
  const [newVenueName, setNewVenueName] = React.useState("");
  const [newVenueCity, setNewVenueCity] = React.useState("Лимасол");
  const [newVenueUrl, setNewVenueUrl] = React.useState("");
  const [newVenueSeats, setNewVenueSeats] = React.useState(50);
  const [poster, setPoster] = React.useState<File | null>(null);
  const [notifyConfirmOpened, setNotifyConfirmOpened] = React.useState(false);
  const [chatTarget, setChatTarget] = React.useState("");
  const [savedChats, setSavedChats] = React.useState<RegistrationChatOption[]>([]);
  const [verifiedChat, setVerifiedChat] = React.useState<{ id: number; title: string; target: string } | null>(null);
  const [checkingChat, setCheckingChat] = React.useState(false);
  const [chatSetupOpened, setChatSetupOpened] = React.useState(false);
  const [previewOpened, setPreviewOpened] = React.useState(false);
  const [activeStep, setActiveStep] = React.useState(0);
  const [draftReadyKey, setDraftReadyKey] = React.useState<string | null>(null);
  const initializedFormRef = React.useRef<string | null>(null);
  const draftKey = showFormDraftKey(initial?.id);
  useShowFormDraft(draftKey, opened && draftReadyKey === draftKey, value, venueId, activeStep);
  const loadRegistrationChats = React.useCallback(async () => {
    if (initial) return;
    try {
      const result = await api<{ items: RegistrationChatOption[] }>("/api/miniapp/registration-chats");
      setSavedChats(result.items);
    } catch { /* The empty state remains actionable; the next resume retries. */ }
  }, [initial]);
  React.useEffect(() => {
    if (!opened) { initializedFormRef.current = null; setDraftReadyKey(null); return; }
    const formKey = initial ? `edit:${initial.id}` : "create";
    if (initializedFormRef.current === formKey) return;
    initializedFormRef.current = formKey;
    const nextValue = initial ? formFromShow(initial) : newShowForm();
    const venue = initial
      ? options.venues.find((item) => item.name === initial.location && item.city === initial.city)
      : undefined;
    if (venue) nextValue.locationUrl = venue.mapsUrl ?? "";
    const draft = readShowFormDraft(draftKey, nextValue);
    setValue(draft?.value ?? nextValue);
    setVenueId(draft?.venueId ?? (venue ? String(venue.id) : initial ? "__custom__" : null));
    setPoster(null); setNotifyConfirmOpened(false); setChatTarget(""); setVerifiedChat(null); setChatSetupOpened(false); setPreviewOpened(false); setTeamDropdownOpened(false); setActiveStep(draft?.activeStep ?? 0); setDraftReadyKey(draftKey);
    if (!initial) void loadRegistrationChats();
  }, [opened, initial, options.venues, loadRegistrationChats, draftKey]);
  useAppResume(() => { void loadRegistrationChats(); }, opened && !initial);
  const set = <K extends keyof ShowFormValue>(key: K, next: ShowFormValue[K]) => setValue((current) => ({ ...current, [key]: next }));
  const selectedVenue = options.venues.find((item) => String(item.id) === venueId);
  const registrarOptions = React.useMemo(() => {
    const team = options.teams.find((item) => item.name === value.teamName);
    const splitMembers = (members: string | null) => (members ?? "").split(/[\s,;]+/)
      .map((username) => username.trim())
      .filter(Boolean)
      .map((username) => username.startsWith("@") ? username : `@${username}`);
    return [...new Set(splitMembers(team?.members ?? null))];
  }, [options.teams, value.teamName]);
  const normalizedRegistrar = value.registrarUsername.trim().replace(/^@?/, "@");
  const registrarIsValid = /^@[A-Za-z][A-Za-z0-9_]{4,31}$/.test(normalizedRegistrar);
  const stepValid = [
    Boolean(value.title.trim() && value.teamName && value.showDateLocal),
    Boolean(venueId && (venueId !== "__custom__" || (value.location.trim() && value.city.trim() && value.maxSeats > 0))),
    Boolean((!value.registrarUsername.trim() || registrarIsValid) && (initial || !chatTarget.trim() || verifiedChat?.target === chatTarget.trim())),
    true,
  ];
  const stepLabels = ["Основное", "Место", "Запись", "Афиша"];

  function changeShowDate(next: string) { set("showDateLocal", next); }

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
      setTeamDropdownOpened(false);
      setTeamModal(false); setNewTeamName(""); setNewTeamMembers("");
      await reloadOptions();
    } catch (reason) { showNotification({ color: "red", title: "Не удалось создать команду", message: (reason as Error).message }); }
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
    } catch (reason) { showNotification({ color: "red", title: "Не удалось создать площадку", message: (reason as Error).message }); }
    finally { setSaving(false); }
  }

  async function verifyRegistrationChat() {
    const target = chatTarget.trim();
    if (!target) return;
    setCheckingChat(true);
    try {
      const result = await api<{ id: number; title: string }>("/api/miniapp/registration-chat/verify", { method: "POST", body: JSON.stringify({ target }) });
      setVerifiedChat({ ...result, target });
      showNotification({ color: "green", title: "Чат проверен", message: `${result.title}: бот подключён` });
    } catch (reason) {
      setVerifiedChat(null);
      showNotification({ color: "red", title: "Чат не прошёл проверку", message: (reason as Error).message });
    } finally { setCheckingChat(false); }
  }

  async function save(notifyViewers: boolean) {
    if (!initial && chatTarget.trim() && verifiedChat?.target !== chatTarget.trim()) {
      showNotification({ color: "red", title: "Сначала проверь чат записей", message: "Бот должен быть добавлен в выбранный чат" });
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
          await api(`/api/miniapp/shows/${result.id}/registration-chat`, { method: "PUT", body: JSON.stringify({ target: String(verifiedChat.id) }) });
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
      showNotification(posterError || chatError
        ? { color: "yellow", title: initial ? "Афиша обновлена частично" : "Афиша создана частично", message: [posterError && "Изображение не загружено", chatError && "Чат записей не подключён"].filter(Boolean).join(" · ") }
        : { color: "gray", title: initial ? "Афиша обновлена" : "Афиша создана", message: "Изменения сохранены" });
      clearShowFormDraft(draftKey);
      setDraftReadyKey(null);
      onSaved(result.id);
    } catch (reason) {
      showNotification({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message });
    } finally { setSaving(false); }
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (activeStep < 3) {
      if (stepValid[activeStep]) setActiveStep((step) => step + 1);
      return;
    }
    if (initial?.hasPublished) setNotifyConfirmOpened(true);
    else void save(false);
  }

  return <Modal
    opened={opened}
    onClose={onClose}
    title={initial ? "Редактировать афишу" : "Новая афиша"}
    size={620}
    xOffset={0}
    yOffset={0}
    transitionProps={{ transition: "slide-up", duration: 240, timingFunction: "ease-out" }}
    classNames={{ inner: "show-form-sheet-inner", content: "show-form-sheet", close: "show-form-close" }}
  >
    <form onSubmit={submit} className="show-form">
      <Stack gap="md">
        <Text size="sm" fw={700}>Шаг {activeStep + 1} из 4 · {stepLabels[activeStep]}</Text>
        <ShowStepper active={activeStep} labels={stepLabels} allowAllSteps={Boolean(initial)} onStepChange={setActiveStep} />
        {activeStep === 0 && <>
        <TextInput required label="Название" value={value.title} onChange={(e) => set("title", e.currentTarget.value)} maxLength={256} />
        <TextInput label="Название для новичков" description="Если оставить пустым, используем обычное название" value={value.titleNewcomer} onChange={(e) => set("titleNewcomer", e.currentTarget.value)} maxLength={256} />
        <Select required searchable allowDeselect={false} label="Команда" data={[...options.teams.map((team) => ({ value: team.name, label: team.name })), { value: "__new__", label: "＋ Добавить новую команду" }]} value={value.teamName || null} dropdownOpened={teamDropdownOpened} onDropdownOpen={() => setTeamDropdownOpened(true)} onDropdownClose={() => setTeamDropdownOpened(false)} onChange={(next) => { setTeamDropdownOpened(false); if (next === "__new__") setTeamModal(true); else set("teamName", next ?? ""); }} />
        <AppDateTimePicker required label="Дата и время" value={value.showDateLocal} onChange={changeShowDate} />
        </>}
        {activeStep === 1 && <>
        <Select required searchable allowDeselect={false} label="Площадка" placeholder="Выбери площадку" data={[...options.venues.map((venue) => ({ value: String(venue.id), label: `${venue.name} · ${venue.city}` })), ...(initial && venueId === "__custom__" ? [{ value: "__custom__", label: `${value.location} · ${value.city}` }] : []), ...(me?.role === "admin" ? [{ value: "__new__", label: "＋ Добавить новую площадку" }] : [])]} value={venueId} onChange={selectVenue} />
        {selectedVenue && <Paper className="venue-summary"><Text fw={700}>{selectedVenue.name}</Text><Text size="sm">{selectedVenue.city} · {selectedVenue.defaultSeats} мест</Text>{selectedVenue.mapsUrl && <Anchor href={selectedVenue.mapsUrl} target="_blank" size="sm">Открыть на карте ↗</Anchor>}</Paper>}
        {venueId === "__custom__" && <><TextInput required label="Название площадки" value={value.location} onChange={(e) => set("location", e.currentTarget.value)} maxLength={512} /><SimpleGrid cols={2}><Autocomplete required label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={value.city} onChange={(next) => set("city", next)} /><NumberInput required min={1} max={10000} label="Количество мест" value={value.maxSeats} onChange={(next) => set("maxSeats", typeof next === "number" ? next : 1)} /></SimpleGrid><TextInput type="url" label="Ссылка на карту" value={value.locationUrl} onChange={(e) => set("locationUrl", e.currentTarget.value)} /></>}
        </>}
        {activeStep === 2 && <>
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
        <NumberInput label="Максимум дополнительных гостей" description="Сколько гостей один зритель может добавить к своей записи" min={0} max={6} value={value.maxGuests} onChange={(next) => set("maxGuests", typeof next === "number" ? next : 0)} />
        {!initial && <Paper className="venue-summary optional-section"><Stack gap="sm">
          <div>
            <Text fw={700}>Чат записей</Text>
            <Text size="sm" c="dimmed">Закрытый рабочий чат организаторов: сюда бот будет присылать новые записи и отмены зрителей. Подключать его необязательно.</Text>
          </div>
          <Switch
            label="Подключить чат записей"
            checked={chatSetupOpened}
            onChange={(event) => {
              const enabled = event.currentTarget.checked;
              setChatSetupOpened(enabled);
              if (!enabled) { setChatTarget(""); setVerifiedChat(null); }
            }}
          />
          <Collapse expanded={chatSetupOpened}><Stack gap="sm" pt="xs">
            <Text size="sm" c="dimmed">Добавь админ-бота в группу или канал. Он подтвердит подключение сообщением, а чат автоматически появится здесь. Если Telegram не прислал событие, отправь в группе <b>/connect_chat</b>.</Text>
            <Select clearable label="Мои чаты" placeholder={savedChats.length ? "Выбери чат" : "Сначала добавь админ-бота в чат"} value={chatTarget || null} onChange={(next) => { setChatTarget(next ?? ""); setVerifiedChat(null); }} data={savedChats.map((chat) => ({ value: String(chat.id), label: chat.title }))} />
            <Button type="button" variant="light" disabled={!chatTarget.trim()} loading={checkingChat} onClick={() => void verifyRegistrationChat()}>{verifiedChat ? `Проверено: ${verifiedChat.title} ✓` : "Проверить выбранный чат"}</Button>
          </Stack></Collapse>
        </Stack></Paper>}
        </>}
        {activeStep === 3 && <>
        <Textarea label="Профессиональное описание" description="Для знакомых с импровом. Жирный текст: **важная фраза**" autosize minRows={5} maxLength={1800} value={value.posterText} onChange={(e) => set("posterText", e.currentTarget.value)} />
        <Textarea label="Описание для новичков" description="Без специальных терминов. Жирный текст: **важная фраза**" autosize minRows={5} maxLength={1800} value={value.posterTextNewcomer} onChange={(e) => set("posterTextNewcomer", e.currentTarget.value)} />
        <FileInput accept="image/jpeg,image/png,image/webp" label="Изображение афиши" description={initial?.hasPoster ? "Выбери файл, чтобы заменить текущее изображение" : "JPEG, PNG или WebP, до 8 МБ"} value={poster} onChange={(file) => { setPoster(file); if (file) setPreviewOpened(true); }} clearable />
        <ShowAutomationSwitches feedbackEnabled={value.feedbackEnabled} checkinEnabled={value.checkinEnabled} onFeedbackChange={(checked) => set("feedbackEnabled", checked)} onCheckinChange={(checked) => set("checkinEnabled", checked)} />
        {value.checkinEnabled && <NumberInput label="Отчёт в чат каждые N человек" min={1} max={100} value={value.checkinReportEvery ?? 10} onChange={(next) => set("checkinReportEvery", Number(next))} />}
        <div className="optional-section"><Button type="button" fullWidth variant="light" onClick={() => setPreviewOpened((opened) => !opened)} aria-expanded={previewOpened}>{previewOpened ? "Скрыть предпросмотр" : "Показать предпросмотр"}</Button><Collapse expanded={previewOpened}><Paper className="telegram-preview"><PosterPreviewImage file={poster} showId={initial?.id} hasExisting={initial?.hasPoster} /><Text size="xs" fw={800} c="dimmed">ПРЕДПРОСМОТР</Text><Title order={3}>🎭 {value.title || "Название шоу"}</Title><Text>👥 Команда: {value.teamName || "не выбрана"}</Text><Text>📅 {value.showDateLocal ? new Date(value.showDateLocal).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" }) : "дата не выбрана"}</Text><Text>📍 {selectedVenue?.name || value.location || "площадка не выбрана"}, {selectedVenue?.city || value.city}</Text>{value.registrarUsername && <Text>👤 Ответственный: {value.registrarUsername}</Text>}{value.posterText && <Text mt="sm" style={{ whiteSpace: "pre-wrap" }}><BoldDescription text={value.posterText} /></Text>}</Paper></Collapse></div>
        </>}
      </Stack>
      <BottomActionBar><Group grow wrap="nowrap">{activeStep > 0 && <Button type="button" variant="default" onClick={() => setActiveStep((step) => step - 1)}>Назад</Button>}<Button type="submit" className="primary" fullWidth loading={saving} size="md" disabled={!stepValid[activeStep]}>{activeStep < 3 ? "Далее" : initial ? "Сохранить изменения" : "Создать афишу"}</Button></Group></BottomActionBar>
    </form>
    <Modal opened={notifyConfirmOpened} onClose={() => setNotifyConfirmOpened(false)} title="Уведомить зрителей?" centered>
      <Text>Отправить записавшимся сообщение об изменениях в афише?</Text>
      <Stack mt="lg" gap="xs">
        <Button className="primary" loading={saving} onClick={() => void save(true)}>Сохранить и уведомить</Button>
        <Button variant="default" disabled={saving} onClick={() => void save(false)}>Сохранить без уведомления</Button>
        <Button variant="subtle" disabled={saving} onClick={() => setNotifyConfirmOpened(false)}>Вернуться к редактированию</Button>
      </Stack>
    </Modal>
    <Modal opened={teamModal} onClose={() => setTeamModal(false)} title="Новая команда" centered><Stack><TextInput required label="Название" value={newTeamName} onChange={(e) => setNewTeamName(e.currentTarget.value)} /><Textarea label="Telegram-ники участников" value={newTeamMembers} onChange={(e) => setNewTeamMembers(e.currentTarget.value)} /><Button disabled={!newTeamName.trim()} loading={saving} onClick={() => void createTeam()}>Создать и выбрать</Button></Stack></Modal>
    <Modal opened={venueModal} onClose={() => setVenueModal(false)} title="Новая площадка" centered><Stack><TextInput required label="Название" value={newVenueName} onChange={(e) => setNewVenueName(e.currentTarget.value)} /><Autocomplete required label="Город" data={["Лимасол", "Никосия", "Пафос"]} value={newVenueCity} onChange={setNewVenueCity} /><NumberInput required min={1} max={10000} label="Количество мест" value={newVenueSeats} onChange={(next) => setNewVenueSeats(typeof next === "number" ? next : 1)} /><TextInput type="url" label="Ссылка на карту" value={newVenueUrl} onChange={(e) => setNewVenueUrl(e.currentTarget.value)} /><Button disabled={!newVenueName.trim() || !newVenueCity.trim()} loading={saving} onClick={() => void createVenue()}>Сохранить для всех и выбрать</Button></Stack></Modal>
  </Modal>;
}
