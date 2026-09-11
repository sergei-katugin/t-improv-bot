import { Anchor, Button, Paper, Stack, Text, Title } from "@mantine/core";
import { openTelegramLink } from "../lib/telegram";

const CONTACT_URL = "https://t.me/sergey_katugin";

function openContact(event: React.MouseEvent) {
  event.preventDefault();
  openTelegramLink(CONTACT_URL);
}

export function AccessDeniedScreen() {
  return <main className="shell access-denied-screen">
    <Paper className="resource-form">
      <Stack align="center" gap="md">
        <Text className="access-denied-icon" aria-hidden="true">🔐</Text>
        <Title order={1} ta="center">Административная Mini App</Title>
        <Text ta="center" c="dimmed">Здесь организаторы создают афиши и управляют записями на шоу.</Text>
        <Text ta="center">Хотите добавить свой анонс? Напишите <Anchor href={CONTACT_URL} onClick={openContact}>@sergey_katugin</Anchor>.</Text>
        <Button component="a" href={CONTACT_URL} onClick={openContact} className="primary">Написать Сергею</Button>
      </Stack>
    </Paper>
  </main>;
}
