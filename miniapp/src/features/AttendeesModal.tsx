import React from "react";
import { Anchor, Button, Group, Modal, Skeleton, Stack, Text, TextInput, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { ShowNavigation } from "../components/ShowNavigation";
import { api } from "../lib/api";
import { useAppResume } from "../hooks/useAppResume";
import type { Attendees, Show } from "../types";
import { previewAttendees } from "./ManagementModal";
import { AttendeeList } from "../components/AttendeeList";

export function AttendeesModal({ opened, onClose, show, demo, backHandlerRef, onEdit, onAnnouncement, onAnalytics, onRegistration, onMore }: {
  opened: boolean; onClose: () => void; show: Show; demo: boolean;
  backHandlerRef: React.MutableRefObject<(() => boolean) | null>;
  onEdit: () => void; onAnnouncement: () => void; onAnalytics: () => void; onRegistration: () => void; onMore: () => void;
}) {
  const [data, setData] = React.useState<Attendees | null>(demo ? previewAttendees : null);
  const [loading, setLoading] = React.useState(!demo);
  const [search, setSearch] = React.useState("");

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
    backHandlerRef.current = null;
    return () => { backHandlerRef.current = null; };
  }, [backHandlerRef]);
  useAppResume(() => { void load(0); }, opened);

  return <Modal opened={opened} onClose={onClose} title={`Зрители · ${show.title}`} fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    {loading && <Stack><Skeleton height={100} /><Skeleton height={100} /></Stack>}
    {data && <Stack gap="md">
      <TextInput aria-label="Фильтр зрителей" placeholder="Имя или @username" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
      <Title order={3}>Записались через бот</Title>
      <AttendeeList items={data.registrations} />
      {data.manual.length > 0 && <><Title order={3}>Добавлены вручную</Title><AttendeeList items={data.manual} /></>}
      {data.waitlist.length > 0 && <><Title order={3}>Лист ожидания · {data.waitlist.length}</Title><div className="attendee-list">{data.waitlist.map((item) => <div className="attendee-list-row" key={item.id}><div><Text fw={700}>{item.name}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}</div><Text size="sm" c="dimmed">№ {item.position}</Text></div>)}</div></>}
      {data.hasMore && <Button variant="default" loading={loading} onClick={() => void load(data.nextOffset, true)}>Показать ещё</Button>}
    </Stack>}
    {data && <ShowNavigation show={show} onShow={onClose} onEdit={onEdit} onAnnouncement={onAnnouncement} onAnalytics={onAnalytics} onRegistration={onRegistration} onMore={onMore} />}
  </Modal>;
}
