import { Badge } from "@mantine/core";

export function AttendeeStatus({ confirmed, checkedInCount, manual = false }: { confirmed?: boolean | null; checkedInCount: number; manual?: boolean }) {
  if (checkedInCount > 0) return <Badge color="green">Пришёл</Badge>;
  if (confirmed === false) return <Badge color="red">Не придёт</Badge>;
  if (confirmed === true) return <Badge color="blue">Подтвердил</Badge>;
  return <Badge color="gray">{manual ? "Добавлен вручную" : "Ожидает ответа"}</Badge>;
}
