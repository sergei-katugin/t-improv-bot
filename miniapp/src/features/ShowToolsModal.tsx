import React from "react";
import { Alert, Anchor, Autocomplete, Badge, Button, Collapse, FileInput, Group, Loader, Modal, NumberInput, Paper, Progress, Select, SimpleGrid, Skeleton, Stack, Switch, Tabs, Text, Textarea, TextInput, Title } from "@mantine/core";
import { BottomActionBar, RootNavigation } from "../components/BottomActionBar";
import { ShowNavigation } from "../components/ShowNavigation";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { ShowStepper } from "../components/ShowStepper";
import { AppDateTimePicker } from "../components/AppDateTimePicker";
import { api, authenticatedBlob } from "../lib/api";
import { showNotification } from "../lib/notifications";
import { telegramConfirm, telegramHaptic } from "../lib/telegram";
import { useAppResume } from "../hooks/useAppResume";
import type { AccessUser, Attendees, AuditItem, Me, Options, Promotion, RegistrationChatOption, Show, ShowFormValue, ThemePreference } from "../types";

export function ShowToolsModal({ mode, opened, onClose, show, registrationUrl, demo, canDeleteActive = false, backHandlerRef, onEdit, onAnalytics, onAnnouncement, onChanged, onDeleted }: {
  mode: "all" | "chat" | "registration"; opened: boolean; onClose: () => void; show: Show; registrationUrl: string; demo: boolean;
  canDeleteActive?: boolean;
  backHandlerRef: React.MutableRefObject<(() => boolean) | null>;
  onEdit: () => void; onAnalytics: () => void; onAnnouncement: () => void; onChanged: (show: Show) => void; onDeleted: () => void;
}) {
  const cloneDefault = React.useMemo(() => {
    const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  }, []);
  const [cloneDate, setCloneDate] = React.useState(cloneDefault);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [cancelConfirm, setCancelConfirm] = React.useState(false);
  const [deleteConfirm, setDeleteConfirm] = React.useState(false);
  const [disconnectChatConfirm, setDisconnectChatConfirm] = React.useState(false);
  const [chatTarget, setChatTarget] = React.useState("");
  const [savedChats, setSavedChats] = React.useState<RegistrationChatOption[]>([]);
  const [tasks, setTasks] = React.useState<{ key: string; label: string; description?: string; count: number }[]>([]);
  const [section, setSection] = React.useState<"menu" | "chat" | "registration" | "clone">("menu");

  React.useEffect(() => {
    if (!opened) return;
    setSection(mode === "chat" ? "chat" : mode === "registration" ? "registration" : "menu");
    if (demo) return;
    api<{ items: { key: string; label: string; description?: string; count: number }[] }>(`/api/miniapp/shows/${show.id}/tasks`).then(({ items }) => setTasks(show.isPast ? [] : items)).catch(() => setTasks([]));
    api<{ items: RegistrationChatOption[] }>("/api/miniapp/registration-chats").then(({ items }) => setSavedChats(items)).catch(() => setSavedChats([]));
  }, [demo, opened, show.id]);
  React.useEffect(() => {
    if (!opened) { backHandlerRef.current = null; return; }
    backHandlerRef.current = () => {
      if (cancelConfirm) { setCancelConfirm(false); return true; }
      if (deleteConfirm) { setDeleteConfirm(false); return true; }
      if (disconnectChatConfirm) { setDisconnectChatConfirm(false); return true; }
      if (mode === "all" && section !== "menu") { setSection("menu"); return true; }
      return false;
    };
    return () => { backHandlerRef.current = null; };
  }, [backHandlerRef, cancelConfirm, deleteConfirm, disconnectChatConfirm, mode, opened, section]);
  useAppResume(() => {
    if (demo) return;
    api<{ items: { key: string; label: string; description?: string; count: number }[] }>(`/api/miniapp/shows/${show.id}/tasks`).then(({ items }) => setTasks(items)).catch(() => undefined);
    api<{ items: RegistrationChatOption[] }>("/api/miniapp/registration-chats").then(({ items }) => setSavedChats(items)).catch(() => undefined);
  }, opened);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(registrationUrl);
      showNotification({ color: "green", title: "Ссылка скопирована", message: "Её можно вставить в любой пост или сообщение" });
    } catch { showNotification({ color: "red", title: "Не удалось скопировать", message: registrationUrl }); }
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
      showNotification({ color: "green", title: "QR-код готов", message: demo ? "В демо скачивание отключено" : "PNG сохранён на устройство" });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось получить QR", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function clone() {
    setBusy("clone");
    try {
      const result = await api<{ id: number }>(`/api/miniapp/shows/${show.id}/clone`, { method: "POST", body: JSON.stringify({ showDateLocal: cloneDate }) });
      showNotification({ color: "green", title: "Копия создана", message: `Новая афиша #${result.id} сохранена на выбранную дату` });
      onClose();
    } catch (reason) { showNotification({ color: "red", title: "Не удалось создать копию", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function cancelShow() {
    setBusy("cancel");
    try {
      const result = demo ? { sent: 12, failed: 0 } : await api<{ sent: number; failed: number }>(`/api/miniapp/shows/${show.id}/cancel`, { method: "POST", body: JSON.stringify({ confirmed: true }) });
      onChanged({ ...show, isActive: false }); setCancelConfirm(false); onClose();
      showNotification({ color: result.failed ? "yellow" : "green", title: "Афиша отменена", message: `Уведомления: доставлено ${result.sent}, ошибок ${result.failed}` });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось отменить афишу", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function restoreShow() {
    setBusy("restore");
    try {
      if (!demo) await api(`/api/miniapp/shows/${show.id}/restore`, { method: "POST" });
      onChanged({ ...show, isActive: true }); onClose();
      showNotification({ color: "green", title: "Афиша восстановлена", message: "Запись снова доступна" });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось восстановить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function deleteShow() {
    setBusy("delete");
    try {
      if (!demo) await api(`/api/miniapp/shows/${show.id}`, { method: "DELETE" });
      setDeleteConfirm(false); onDeleted();
      showNotification({ color: "green", title: "Афиша удалена", message: "Связанные данные удалены" });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось удалить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function saveRegistrationChat() {
    setBusy("chat");
    try {
      const result = await api<{ id: number; title: string; nameMode: "full" }>(`/api/miniapp/shows/${show.id}/registration-chat`, { method: "PUT", body: JSON.stringify({ target: chatTarget }) });
      onChanged({ ...show, registrationChatId: result.id, registrationChatTitle: result.title, registrationChatNameMode: result.nameMode });
      setChatTarget(""); showNotification({ color: "green", title: "Рабочий чат подключён", message: result.title });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось подключить чат", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function clearRegistrationChat() {
    setBusy("chat");
    try {
      await api(`/api/miniapp/shows/${show.id}/registration-chat`, { method: "DELETE" });
      onChanged({ ...show, registrationChatId: null, registrationChatTitle: null });
      setDisconnectChatConfirm(false);
      showNotification({ color: "green", title: "Рабочий чат отключён", message: "Уведомления о записях больше не отправляются" });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось отключить чат", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  async function confirmManualNotifications() {
    setBusy("manual-confirm");
    try {
      const result = await api<{ confirmed: number }>(`/api/miniapp/shows/${show.id}/manual-notifications/confirm`, { method: "POST" });
      setTasks((current) => current.filter((item) => item.key !== "manual_notifications"));
      showNotification({ color: "green", title: "Отмечено", message: `Уведомлены вручную: ${result.confirmed}` });
    } catch (reason) { showNotification({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message }); }
    finally { setBusy(null); }
  }

  function openTask(key: string) {
    if (key === "announcement" || key === "repeat_announcement") { onClose(); onAnnouncement(); }
    else if (key === "show_responsible") { onClose(); onEdit(); }
    else if (key === "registration_chat") setSection("chat");
    else if (key === "manual_notifications") void confirmManualNotifications();
  }

  const sectionTitle = section === "menu" ? (show.isPast ? "Настройки" : "Действия") : section === "chat" ? "Чат записей" : section === "registration" ? "Ссылка и QR" : "Создать копию";
  const title = `${sectionTitle} · ${show.title}`;
  return <Modal opened={opened} onClose={onClose} title={title} fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    {section !== "menu" && mode === "all" && <Button className="back" variant="subtle" onClick={() => setSection("menu")}>← Все действия</Button>}
    {section === "menu" && <Stack gap="xs" className="tools-menu">
      {tasks.length > 0 && <><Text className="tools-section-label">Требуют внимания · {tasks.length}</Text>{tasks.map((task) => <button key={task.key} className="tools-menu-action attention" disabled={busy !== null} onClick={() => openTask(task.key)}><span><b>{task.label}</b><small>{task.description ?? (task.count > 1 ? `${task.count} элементов` : "Открыть и выполнить")}</small></span><span>→</span></button>)}</>}
      {!show.isPast && <button className="tools-menu-action" onClick={() => setSection("chat")}><span><b>Чат записей</b><small>{show.registrationChatId ? show.registrationChatTitle || "Подключён" : "Не подключён"}</small></span><span>→</span></button>}
      {!show.isPast && show.hasPublished && <button className="tools-menu-action" onClick={() => { onClose(); onAnnouncement(); }}><span><b>Анонс</b><small>Посмотреть или опубликовать повторно</small></span><span>→</span></button>}
      {!show.isPast && !show.hasPublished && <button className="tools-menu-action" onClick={onAnalytics}><span><b>Аналитика</b><small>Записи, посещаемость и отзывы</small></span><span>→</span></button>}
      {!show.isPast && <button className="tools-menu-action" onClick={() => setSection("registration")}><span><b>Ссылка и QR</b><small>Для самостоятельной записи зрителей</small></span><span>→</span></button>}
      <button className="tools-menu-action" onClick={() => setSection("clone")}><span><b>Создать копию</b><small>Новая афиша с теми же данными</small></span><span>→</span></button>
      {show.isPast ? <button className="tools-menu-action danger" onClick={() => setDeleteConfirm(true)}><span><b>Удалить навсегда</b><small>Удалить афишу и связанные данные</small></span><span>→</span></button> : show.isActive ? <><button className="tools-menu-action danger" onClick={() => setCancelConfirm(true)}><span><b>Отменить афишу</b><small>Закрыть запись и уведомить зрителей</small></span><span>→</span></button>{canDeleteActive && <button className="tools-menu-action danger" onClick={() => setDeleteConfirm(true)}><span><b>Удалить навсегда</b><small>Доступно только суперадмину</small></span><span>→</span></button>}</> : <><button className="tools-menu-action" onClick={() => void restoreShow()}><span><b>Восстановить афишу</b><small>Снова открыть запись</small></span><span>→</span></button><button className="tools-menu-action danger" onClick={() => setDeleteConfirm(true)}><span><b>Удалить навсегда</b><small>Удалить афишу и связанные данные</small></span><span>→</span></button></>}
    </Stack>}
    {section === "chat" && <Stack><Text size="sm" c="dimmed">Сюда бот будет отправлять сообщения о новых записях.</Text>{show.registrationChatId ? <Paper className="resource-card"><Text fw={750}>{show.registrationChatTitle || show.registrationChatId}</Text><Text size="sm" c="dimmed">Чат подключён</Text></Paper> : <><Text size="sm" c="dimmed">Добавь админ-бота в группу или канал — чат автоматически появится в списке.</Text><Select clearable label="Мои чаты" placeholder={savedChats.length ? "Выбери чат" : "Подключённых чатов пока нет"} value={chatTarget || null} onChange={(value) => setChatTarget(value ?? "")} data={savedChats.map((chat) => ({ value: String(chat.id), label: chat.title }))} /></>}</Stack>}
    {section === "registration" && <Stack><Text size="sm" c="dimmed">Ссылка открывает публичного бота сразу на записи на это шоу. QR-код содержит ту же ссылку.</Text><Paper className="resource-card"><Text size="sm" style={{ wordBreak: "break-all" }}>{registrationUrl}</Text></Paper><Group className="announcement-actions" grow wrap="nowrap"><Button variant="light" onClick={() => void copyLink()}>Копировать</Button><Button className="primary" loading={busy === "qr"} onClick={() => void downloadQr()}>Скачать QR</Button></Group></Stack>}
    {section === "clone" && <Stack><Text size="sm" c="dimmed">Будет создана новая неопубликованная афиша с теми же данными.</Text><AppDateTimePicker label="Дата и время новой афиши" value={cloneDate} onChange={setCloneDate} /></Stack>}
    {section === "chat" && <BottomActionBar>{show.registrationChatId ? <Button color="red" variant="light" fullWidth loading={busy === "chat"} onClick={() => setDisconnectChatConfirm(true)}>Отключить чат</Button> : <Button className="primary" fullWidth disabled={!chatTarget.trim()} loading={busy === "chat"} onClick={() => void saveRegistrationChat()}>Подключить чат</Button>}</BottomActionBar>}
    {section === "clone" && <BottomActionBar><Button className="primary" fullWidth loading={busy === "clone"} onClick={() => void clone()}>Создать копию</Button></BottomActionBar>}
    {(section === "menu" || section === "registration") && <ShowNavigation show={show} active={section === "menu" ? "more" : "registration"} onShow={onClose} onEdit={onEdit} onAnnouncement={onAnnouncement} onAnalytics={onAnalytics} onRegistration={() => setSection("registration")} onMore={() => setSection("menu")} />}
    <Modal opened={cancelConfirm} onClose={() => setCancelConfirm(false)} title="Точно отменить афишу?" centered><Text>Действие закроет новые записи и отправит уведомления зрителям.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setCancelConfirm(false)}>Не отменять</Button><Button color="red" loading={busy === "cancel"} onClick={() => void cancelShow()}>Да, отменить</Button></Group></Modal>
    <Modal opened={deleteConfirm} onClose={() => setDeleteConfirm(false)} title="Удалить афишу навсегда?" centered><Text>Будут удалены записи, отзывы и история анонсов. Это действие нельзя отменить.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setDeleteConfirm(false)}>Не удалять</Button><Button color="red" loading={busy === "delete"} onClick={() => void deleteShow()}>Удалить навсегда</Button></Group></Modal>
    <Modal opened={disconnectChatConfirm} onClose={() => setDisconnectChatConfirm(false)} title="Отключить чат записей?" centered><Text>Бот сообщит об отключении в рабочем чате. Новые записи и отмены больше не будут туда приходить.</Text><Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setDisconnectChatConfirm(false)}>Не отключать</Button><Button color="red" loading={busy === "chat"} onClick={() => void clearRegistrationChat()}>Отключить</Button></Group></Modal>
  </Modal>;
}
