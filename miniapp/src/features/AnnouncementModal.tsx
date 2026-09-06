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

export function AnnouncementModal({ opened, onClose, show, demo, onEdit, onAnalytics, onRegistration, onMore, onPublished }: {
  opened: boolean; onClose: () => void; show: Show; demo: boolean; onEdit: () => void; onAnalytics: () => void; onRegistration: () => void; onMore: () => void; onPublished: () => void;
}) {
  const [html, setHtml] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [publishing, setPublishing] = React.useState(false);
  const [sendingTest, setSendingTest] = React.useState(false);
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
      }
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось открыть предпросмотр", message: (reason as Error).message }); }
    finally { setLoading(false); }
  }, [demo, show]);

  React.useEffect(() => {
    if (opened) void load();
  }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps
  useAppResume(() => { void load(); }, opened);

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
      onPublished();
      setRepeatConfirm(false);
      notifications.show({ color: "green", title: repeat ? "Анонс отправлен повторно" : "Анонс опубликован", message: "Пост отправлен в основной канал с кнопкой записи" });
    } catch (reason) { notifications.show({ color: "red", title: "Не удалось опубликовать", message: (reason as Error).message }); }
    finally { setPublishing(false); }
  }

  async function copyPromotion() {
    if (!promotion) return;
    try {
      await navigator.clipboard.writeText(promotion.text);
      notifications.show({ color: "green", title: "Текст и ссылка скопированы", message: "Можно вставить их в соцсеть, канал или чат" });
    } catch { notifications.show({ color: "red", title: "Не удалось скопировать", message: "Выдели текст анонса вручную" }); }
  }

  async function sendTestAnnouncement() {
    setSendingTest(true);
    try {
      if (!demo) await api(`/api/miniapp/shows/${show.id}/promotion/test`, { method: "POST" });
      notifications.show({ color: "green", title: "Тест отправлен", message: "Проверь личный чат с админ-ботом" });
    } catch (reason) {
      notifications.show({ color: "red", title: "Не удалось отправить тест", message: (reason as Error).message });
    } finally { setSendingTest(false); }
  }

  return <Modal opened={opened} onClose={onClose} title="Предпросмотр анонса" fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    <Stack gap="md">
      {loading && <Skeleton height={240} radius="lg" />}
      {!loading && <Paper className="telegram-preview" dangerouslySetInnerHTML={{ __html: html }} />}
      {!loading && promotion && <Paper className="resource-form"><Stack>
        <Title order={3}>Публикация</Title>
        {!promotion.hasPublished ?
          <Text size="sm" c="dimmed">После проверки опубликуй готовый анонс.</Text> :
          <Alert color="green">Анонс уже публиковался. Если до шоу осталось мало времени и есть свободные места, его можно отправить повторно.</Alert>}
        <Button variant="default" loading={sendingTest} onClick={() => void sendTestAnnouncement()}>Отправить тест себе</Button>
        <Text size="xs" c="dimmed">Придёт только тебе в личный чат с админ-ботом и не будет считаться публикацией.</Text>
        <Button variant="default" onClick={() => void copyPromotion()}>Скопировать текст и ссылку</Button>
        <Text size="xs" c="dimmed">Готовая версия для другой соцсети, канала или чата. Ссылка на запись уже добавлена.</Text>
        <Button className="primary" loading={publishing} onClick={() => promotion.hasPublished ? setRepeatConfirm(true) : void publish()}>{promotion.hasPublished ? "Опубликовать повторно" : "Опубликовать в основном канале"}</Button>
      </Stack></Paper>}
      {!loading && promotion && <Paper className="resource-form"><Stack>
        <Title order={3}>Рекламные каналы</Title>
        <Text size="sm" c="dimmed">При копировании Telegram не переносит inline-кнопку. Поэтому в текст добавлена прямая ссылка на запись — она останется кликабельной.</Text>
        {promotion.channels.length ? promotion.channels.map((channel) => <Button key={channel.id} component="a" href={channel.url} target="_blank" variant="default">Открыть @{channel.username.replace(/^@/, "")}</Button>) : <Text size="sm" c="dimmed">Активные рекламные каналы пока не добавлены.</Text>}
      </Stack></Paper>}
    </Stack>
    <ShowNavigation show={show} active="announcement" onShow={onClose} onEdit={onEdit} onAnnouncement={() => undefined} onAnalytics={onAnalytics} onRegistration={onRegistration} onMore={onMore} />
    <Modal opened={repeatConfirm} onClose={() => setRepeatConfirm(false)} title="Повторить публикацию?" centered>
      <Text>В основной канал будет отправлена ещё одна полноценная афиша с кнопкой записи.</Text>
      <Group justify="flex-end" mt="lg"><Button variant="default" onClick={() => setRepeatConfirm(false)}>Отмена</Button><Button color="orange" loading={publishing} onClick={() => void publish(true)}>Да, отправить повторно</Button></Group>
    </Modal>
  </Modal>;
}
