import React from "react";
import { Anchor, Button, Group, Modal, NumberInput, Select, Skeleton, Stack, Text, TextInput, Title } from "@mantine/core";
import { ShowNavigation } from "../components/ShowNavigation";
import { api } from "../lib/api";
import { showNotification } from "../lib/notifications";
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
  const [addOpened, setAddOpened] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [manual, setManual] = React.useState({ name: "", source: "telegram", contact: "", guests: 0 });

  const load = React.useCallback(async (cursor: string | null = null, append = false) => {
    if (demo) { setData(previewAttendees); return; }
    setLoading(true);
    try {
      const query = new URLSearchParams();
      if (cursor) query.set("cursor", cursor);
      if (search.trim()) query.set("search", search.trim());
      const next = await api<Attendees>(`/api/miniapp/shows/${show.id}/attendees?${query}`);
      setData((current) => append && current ? {
        ...next,
        registrations: [...current.registrations, ...next.registrations],
        manual: [...current.manual, ...next.manual],
        waitlist: current.waitlist,
      } : next);
    }
    catch (reason) { showNotification({ color: "red", title: "Не удалось загрузить записи", message: (reason as Error).message }); }
    finally { setLoading(false); }
  }, [demo, search, show.id]);

  React.useEffect(() => { if (opened) void load(); }, [opened, load]);
  React.useEffect(() => {
    backHandlerRef.current = null;
    return () => { backHandlerRef.current = null; };
  }, [backHandlerRef]);
  useAppResume(() => { void load(null); }, opened);

  const addAttendee = async () => {
    setSaving(true);
    try {
      await api(`/api/miniapp/shows/${show.id}/attendees/manual`, {
        method: "POST", body: JSON.stringify(manual),
      });
      showNotification({ color: "green", title: "Зритель добавлен", message: "Запись сохранена" });
      setManual({ name: "", source: "telegram", contact: "", guests: 0 });
      setAddOpened(false);
      await load();
    } catch (reason) {
      showNotification({ color: "red", title: "Не удалось добавить зрителя", message: (reason as Error).message });
    } finally { setSaving(false); }
  };

  return <Modal opened={opened} onClose={onClose} title={`Зрители · ${show.title}`} fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    {loading && <Stack><Skeleton height={100} /><Skeleton height={100} /></Stack>}
    {data && <Stack gap="md">
      <Button onClick={() => setAddOpened(true)}>➕ Добавить человека</Button>
      <TextInput aria-label="Фильтр зрителей" placeholder="Имя или @username" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
      <Title order={3}>Записались через бот</Title>
      <AttendeeList items={data.registrations} />
      {data.manual.length > 0 && <><Title order={3}>Добавлены вручную</Title><AttendeeList items={data.manual} /></>}
      {data.waitlist.length > 0 && <><Title order={3}>Лист ожидания · {data.waitlist.length}</Title><div className="attendee-list">{data.waitlist.map((item) => <div className="attendee-list-row" key={item.id}><div><Text fw={700}>{item.name}</Text>{item.username && <Anchor size="sm" href={`https://t.me/${item.username}`} target="_blank">@{item.username}</Anchor>}</div><Text size="sm" c="dimmed">№ {item.position}</Text></div>)}</div></>}
      {data.hasMore && <Button variant="default" loading={loading} onClick={() => void load(data.nextCursor ?? null, true)}>Показать ещё</Button>}
    </Stack>}
    <Modal opened={addOpened} onClose={() => setAddOpened(false)} title="Добавить человека" centered>
      <Stack>
        <TextInput label="Полное имя" value={manual.name} onChange={(event) => setManual({ ...manual, name: event.currentTarget.value })} />
        <Select label="Где связаться" value={manual.source} onChange={(value) => setManual({ ...manual, source: value ?? "other" })}
          data={[{ value: "telegram", label: "Telegram" }, { value: "instagram", label: "Instagram" }, { value: "other", label: "Другое" }]} />
        <TextInput label="Контакт" placeholder={manual.source === "telegram" ? "@username" : manual.source === "instagram" ? "@username" : "Телефон или ссылка"}
          value={manual.contact} onChange={(event) => setManual({ ...manual, contact: event.currentTarget.value })} />
        <NumberInput label="Дополнительные гости" min={0} max={Math.min(6, show.maxGuests ?? 6)} value={manual.guests}
          onChange={(value) => setManual({ ...manual, guests: typeof value === "number" ? value : 0 })} />
        <Group justify="flex-end"><Button variant="default" onClick={() => setAddOpened(false)}>Отмена</Button>
          <Button loading={saving} disabled={manual.name.trim().length < 2 || manual.contact.trim().length < 2} onClick={() => void addAttendee()}>Добавить</Button></Group>
      </Stack>
    </Modal>
    {data && <ShowNavigation show={show} onShow={onClose} onEdit={onEdit} onAnnouncement={onAnnouncement} onAnalytics={onAnalytics} onRegistration={onRegistration} onMore={onMore} />}
  </Modal>;
}
