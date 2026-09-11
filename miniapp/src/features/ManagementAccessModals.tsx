import { Alert, Anchor, Badge, Button, Group, Loader, Modal, Paper, Stack, Text, Title } from "@mantine/core";
import { BottomActionBar } from "../components/BottomActionBar";
import type { AccessUser, AuditItem } from "../types";

export function AccessModal({ opened, onClose, users, loading, inviteUrl, saving, onInvite, onCopy, onAudit, onRevoke }: {
  opened: boolean; onClose: () => void; users: AccessUser[]; loading: boolean;
  inviteUrl: string | null; saving: boolean; onInvite: () => void; onCopy: () => void;
  onAudit: () => void; onRevoke: (user: AccessUser) => void;
}) {
  return <Modal opened={opened} onClose={onClose} title="Доступ и журнал" size={620} xOffset={0} yOffset={0}
    transitionProps={{ transition: "slide-up", duration: 240, timingFunction: "ease-out" }}
    closeButtonProps={{ "aria-label": "Закрыть доступ и журнал" }}
    classNames={{ inner: "show-form-sheet-inner", content: "access-sheet", close: "show-form-close" }}>
    <Stack>
      <Paper className="resource-form"><Stack><Title order={3}>Пригласить организатора</Title><Text size="sm" c="dimmed">Ссылка одноразовая и автоматически истечёт. Новый пользователь сможет управлять только созданными им афишами.</Text>{inviteUrl && <Text size="sm" style={{ wordBreak: "break-all" }}>{inviteUrl}</Text>}</Stack></Paper>
      <Title order={3}>Пользователи с доступом</Title>
      {loading && <Loader size="sm" />}
      {!loading && users.map((user) => <Paper className="resource-card" key={user.id}><Group justify="space-between" align="flex-start"><div><Group gap="xs"><Text fw={750}>{[user.firstName, user.lastName].filter(Boolean).join(" ") || user.username || user.telegramId}</Text><Badge color={user.role === "admin" ? "yellow" : "gray"}>{user.role === "admin" ? "Администратор" : "Организатор"}</Badge>{user.isCurrent && <Badge color="gray">Вы</Badge>}</Group>{user.username && <Anchor size="sm" href={`https://t.me/${user.username}`} target="_blank">@{user.username}</Anchor>}</div>{!user.isProtected && !user.isCurrent && <Button size="xs" color="red" variant="subtle" onClick={() => onRevoke(user)}>Отозвать</Button>}</Group></Paper>)}
      {!loading && !users.length && <Text c="dimmed">Пользователей с доступом нет.</Text>}
      <Button variant="default" onClick={onAudit}>Журнал действий</Button>
      <BottomActionBar inline>{inviteUrl ? <Button className="primary" fullWidth onClick={onCopy}>Копировать приглашение</Button> : <Button className="primary" fullWidth loading={saving} onClick={onInvite}>＋ Пригласить организатора</Button>}</BottomActionBar>
    </Stack>
  </Modal>;
}

const auditLabels: Record<string, string> = {
  "show.published": "Афиша опубликована", "show.republished": "Афиша опубликована повторно",
  "show.cancelled": "Афиша отменена", "show.cloned": "Создана копия афиши",
  "access.invite_created": "Создано приглашение", "access.role_changed": "Изменена роль пользователя",
};

export function AuditLogModal({ opened, onClose, items, loading, error, onReload }: {
  opened: boolean; onClose: () => void; items: AuditItem[]; loading: boolean;
  error: string | null; onReload: () => void;
}) {
  return <Modal opened={opened} onClose={onClose} title="Журнал действий" size={620} xOffset={0} yOffset={0}
    transitionProps={{ transition: "slide-up", duration: 240, timingFunction: "ease-out" }}
    closeButtonProps={{ "aria-label": "Закрыть журнал действий" }}
    classNames={{ inner: "show-form-sheet-inner", content: "audit-sheet", close: "show-form-close" }}>
    <Stack>
      <Group justify="space-between" align="center"><Text size="sm" c="dimmed">Последние 100 административных операций Mini App</Text><Button size="xs" variant="light" loading={loading} onClick={onReload}>Обновить</Button></Group>
      {error && <Alert color="red" title="Не удалось загрузить журнал">{error}<Button mt="sm" size="xs" variant="light" color="red" onClick={onReload}>Повторить</Button></Alert>}
      {loading && !items.length && <Loader size="sm" />}
      {items.map((item) => {
        const actorName = item.actor?.username ? `@${item.actor.username}` : item.actor?.firstName || "Удалённый пользователь";
        return <Paper className="resource-card" key={item.id}><Group justify="space-between" align="flex-start"><div><Text fw={750}>{auditLabels[item.action] ?? item.action}</Text><Text size="sm" c="dimmed">{actorName} · {new Date(item.createdAt).toLocaleString("ru-RU")}</Text></div><Badge variant="light">{item.entityType} #{item.entityId ?? "—"}</Badge></Group>{item.details && <Text size="xs" c="dimmed" mt="sm" style={{ wordBreak: "break-word" }}>{Object.entries(item.details).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</Text>}</Paper>;
      })}
      {!loading && !items.length && <Text c="dimmed">Журнал пока пуст.</Text>}
    </Stack>
  </Modal>;
}
