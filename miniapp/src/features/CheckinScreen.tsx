import React from "react";
import { Alert, Button, Group, Loader, Modal, NumberInput, Paper, Progress, Select, Stack, Text, TextInput, Title } from "@mantine/core";
import { api } from "../lib/api";
import { showNotification } from "../lib/notifications";

type Entry = { kind: "registration" | "manual"; id: number; name: string; booked: number; arrived: number };
type Arrivals = { id: number; title: string; mode: "counter" | "named"; reportEvery: number; arrived: number; booked: number; remaining: number; percent: number; items: Entry[] };

export function CheckinScreen({ showId, canConfigure = false }: { showId: number; canConfigure?: boolean }) {
  const [data, setData] = React.useState<Arrivals | null>(null);
  const [search, setSearch] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [mode, setMode] = React.useState<"counter" | "named">("named");
  const [step, setStep] = React.useState(10);
  const [invite, setInvite] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState(false);
  const sequence = React.useRef(0);
  const load = React.useCallback(async () => {
    const current = ++sequence.current;
    try {
      const next = await api<Arrivals>(`/api/miniapp/shows/${showId}/checkin?search=${encodeURIComponent(search)}`);
      if (current === sequence.current) { setData(next); setError(null); }
    } catch (reason) { if (current === sequence.current) setError((reason as Error).message); }
  }, [search, showId]);
  React.useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    const poll = window.setInterval(() => void load(), 10000);
    return () => { window.clearTimeout(timer); window.clearInterval(poll); sequence.current++; };
  }, [load]);
  async function perform(path: string, body: object, method = "POST") {
    if (busy) return;
    setBusy(true);
    try { await api(`/api/miniapp/shows/${showId}/checkin${path}`, { method, body: JSON.stringify({ expected: data?.arrived, ...body }) }); await load(); return true; }
    catch (reason) { showNotification({ color: "red", title: "Не удалось сохранить", message: (reason as Error).message }); await load(); return false; }
    finally { setBusy(false); }
  }
  async function createInvite() {
    setBusy(true);
    try {
      const result = await api<{ url: string }>(`/api/miniapp/shows/${showId}/checkin/invite`, { method: "POST", body: "{}" });
      setInvite(result.url);
    } catch (reason) { showNotification({ color: "red", title: "Не удалось создать приглашение", message: (reason as Error).message }); }
    finally { setBusy(false); }
  }
  if (!data) return error ? <Alert color="red">{error}<Button onClick={() => void load()}>Повторить</Button></Alert> : <Loader aria-label="Загружаем вход" />;
  return <Stack>
    <Title order={1}>Вход · {data.title}</Title>
    {error && <Alert color="red">{error}</Alert>}
    <Paper p="lg" withBorder><Title order={2}>Пришли и ждут: {data.arrived}</Title><Text>Из {data.booked} записанных · {data.percent}%</Text><Progress value={Math.min(100, data.percent)} mt="sm" /><Text mt="sm">Ещё не пришли: {data.remaining}</Text></Paper>
    <Text c="dimmed">Отчёт в чат записей — каждые {data.reportEvery} человек. В простом режиме процент приблизительный: имена не проверяются.</Text>
    {data.mode === "counter" ? <Group grow>{[1, 2, 3].map((delta) => <Button key={delta} size="xl" disabled={busy} onClick={() => void perform("", { delta })}>+{delta}</Button>)}<Button variant="default" disabled={busy || !data.arrived} onClick={() => void perform("", { delta: -1 })}>−1</Button></Group> : <>
      <TextInput label="Поиск зрителя" placeholder="Имя, фамилия или Telegram-ник" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
      {!data.items.length && <Text>Никого не найдено.</Text>}
      {data.items.map((item) => <Paper key={`${item.kind}:${item.id}`} p="md" withBorder><Text fw={700}>{item.name}</Text><Text>Пришло {item.arrived} из {item.booked}</Text><Group mt="sm"><Button disabled={busy || item.arrived >= item.booked} onClick={() => void perform("", { ...item, count: item.arrived + 1 })}>Пришёл +1</Button><Button variant="light" disabled={busy || item.arrived === item.booked} onClick={() => void perform("", { ...item, count: item.booked })}>Пришли все</Button><Button variant="subtle" disabled={busy || !item.arrived} onClick={() => void perform("", { ...item, count: item.arrived - 1 })}>−1</Button></Group></Paper>)}
      <Text size="sm" c="dimmed">Показаны до 50 записей каждого типа. Остальных найди поиском.</Text>
    </>}
    {canConfigure && <>
      <Button variant="default" onClick={() => { setMode(data.mode); setStep(data.reportEvery); setEditing(true); }}>Настроить режим входа</Button>
      <Button loading={busy} onClick={() => void createInvite()}>Пригласить сотрудника входа</Button>
      {invite && <><Text>Одноразовая ссылка, действует 24 часа. Доступ только к входу этого шоу.</Text><TextInput readOnly label="Ссылка сотруднику" value={invite} /><Button onClick={() => void navigator.clipboard.writeText(invite).catch(() => setError("Не удалось скопировать ссылку"))}>Скопировать приглашение</Button></>}
      <Modal opened={editing} onClose={() => setEditing(false)} title="Настройки входа"><Stack><Select label="Режим" value={mode} onChange={(value) => setMode(value as "named" | "counter")} data={[{ value: "counter", label: "Простой — счётчик +1 / +2 / +3" }, { value: "named", label: "По именам — поиск и отметка записи" }]} /><NumberInput label="Отчёт каждые N человек" min={1} max={100} value={step} onChange={(value) => setStep(Number(value))} /><Text size="sm">После начала входа сменить режим нельзя.</Text><Button loading={busy} onClick={() => void perform("/config", { mode, reportEvery: step }, "PUT").then((saved) => { if (saved) setEditing(false); })}>Сохранить</Button></Stack></Modal>
    </>}
  </Stack>;
}

export function CheckinHome() {
  const [shows, setShows] = React.useState<{ id: number; title: string; date: string }[]>([]);
  const [selected, setSelected] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => { api<{ items: typeof shows }>("/api/miniapp/checkin/shows").then(({ items }) => { setShows(items); if (items.length === 1) setSelected(items[0]!.id); }).catch((reason) => setError(reason.message)); }, []);
  return <main className="shell">{selected ? <><Button variant="subtle" onClick={() => setSelected(null)}>← Доступные шоу</Button><CheckinScreen key={selected} showId={selected} /></> : <Stack><Title order={1}>Сотрудник входа</Title>{error && <Alert color="red">{error}</Alert>}{shows.map((show) => <Button key={show.id} onClick={() => setSelected(show.id)}>{show.title} · {show.date}</Button>)}{!shows.length && <Text>Нет активных шоу с доступом к входу.</Text>}</Stack>}</main>;
}
