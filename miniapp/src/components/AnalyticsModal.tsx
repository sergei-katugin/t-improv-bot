import React from "react";
import { Alert, Anchor, Badge, Button, Group, Modal, Paper, Progress, SimpleGrid, Skeleton, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { api, authenticatedBlob } from "../lib/api";
import { useAppResume } from "../hooks/useAppResume";
import type { Analytics, Show } from "../types";
import { BottomActionBar } from "./BottomActionBar";

export function AnalyticsModal({ opened, onClose, show, demo }: { opened: boolean; onClose: () => void; show: Show; demo: boolean }) {
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
  useAppResume(() => { void load(); }, opened);
  const sourceLabels: Record<string, string> = { direct: "Через бота", manual: "Вручную", social: "Другие соцсети", instagram: "Instagram", channel: "Telegram-канал", team: "Команда" };
  const maxRating = data ? Math.max(1, ...Object.values(data.ratingDistribution)) : 1;

  async function downloadCsv() {
    try {
      if (demo) {
        notifications.show({ color: "gray", title: "Демо-режим", message: "Экспорт доступен после запуска из Telegram" });
        return;
      }
      const blob = await authenticatedBlob(`/api/miniapp/shows/${show.id}/export.csv`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `show-${show.id}-attendees.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      notifications.show({ color: "red", title: "Не удалось скачать CSV", message: (reason as Error).message });
    }
  }

  return <Modal opened={opened} onClose={onClose} title={`Аналитика · ${show.title}`} fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    {loading && <Stack><Skeleton height={120} radius="lg" /><Skeleton height={220} radius="lg" /></Stack>}
    {!loading && error && <Alert color="red" title="Не удалось загрузить аналитику">{error}<Button mt="sm" size="xs" variant="light" color="red" onClick={() => void load()}>Повторить</Button></Alert>}
    {!loading && data && <Stack>
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
    {!loading && data && <BottomActionBar><Button className="primary" fullWidth onClick={() => void downloadCsv()}>Скачать отчёт · CSV</Button></BottomActionBar>}
  </Modal>;
}
