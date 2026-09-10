import { Button, Paper, Text, Title } from "@mantine/core";

export function EmptyShowsState({
  status,
  onCreate,
}: {
  status: "upcoming" | "past";
  onCreate: () => void;
}) {
  return <Paper className="state empty-shows-state">
    <span className="empty-shows-icon" aria-hidden="true">
      <svg viewBox="0 0 48 48">
        <rect x="7" y="9" width="34" height="32" rx="8" />
        <path d="M15 6v7M33 6v7M7 18h34M24 24v11M18.5 29.5h11" />
      </svg>
    </span>
    <Title order={3}>{status === "upcoming" ? "Здесь пока пусто" : "Прошедших афиш пока нет"}</Title>
    {status === "upcoming" ? <>
      <Text>Создай первую афишу — она появится в этом разделе.</Text>
      <Button className="primary empty-shows-create" size="md" onClick={onCreate}>
        Создать афишу
      </Button>
    </> : <Text>Здесь появятся завершённые события.</Text>}
  </Paper>;
}
