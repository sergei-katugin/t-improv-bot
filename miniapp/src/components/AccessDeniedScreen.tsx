import { Anchor, Button, Paper, Stack, Text, Title } from "@mantine/core";

export function AccessDeniedScreen() {
  return <main className="shell access-denied-screen">
    <Paper className="resource-form">
      <Stack align="center" gap="md">
        <Text className="access-denied-icon" aria-hidden="true">🔐</Text>
        <Title order={1} ta="center">Административная Mini App</Title>
        <Text ta="center" c="dimmed">Здесь организаторы создают афиши и управляют записями на шоу.</Text>
        <Text ta="center">Хотите добавить свой анонс? Напишите <Anchor href="https://t.me/sergey_katugin" target="_blank">@sergey_katugin</Anchor>.</Text>
        <Button component="a" href="https://t.me/sergey_katugin" target="_blank" className="primary">Написать Сергею</Button>
      </Stack>
    </Paper>
  </main>;
}
