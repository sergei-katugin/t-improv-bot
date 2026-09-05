import React from "react";
import { Button, Modal, Paper, SegmentedControl, Stack, Text, Title } from "@mantine/core";
import type { ThemePreference } from "../types";

export function AppearanceSettings({ value, onChange, onReset }: { value: ThemePreference; onChange: (value: ThemePreference) => void; onReset: () => void }) {
  const [confirmOpened, setConfirmOpened] = React.useState(false);
  return <Stack gap="md"><Paper className="resource-form">
    <Stack gap="sm">
      <div>
        <Title order={3}>Тема оформления</Title>
        <Text size="sm" c="dimmed">Системная тема следует настройке Telegram и меняется вместе с ней.</Text>
      </div>
      <SegmentedControl
        fullWidth
        value={value}
        onChange={(next) => onChange(next as ThemePreference)}
        data={[
          { label: "Системная", value: "system" },
          { label: "Светлая", value: "light" },
          { label: "Тёмная", value: "dark" },
        ]}
      />
    </Stack>
  </Paper>
    <Paper className="resource-form"><Stack gap="sm">
      <div><Title order={3}>Сбросить Mini App</Title><Text size="sm" c="dimmed">Очистит тему, локальные данные и снова покажет онбординг. Афиши и записи не удаляются.</Text></div>
      <Button color="red" variant="light" onClick={() => setConfirmOpened(true)}>Сбросить локальные данные</Button>
    </Stack></Paper>
    <Modal opened={confirmOpened} onClose={() => setConfirmOpened(false)} title="Сбросить Mini App?" centered>
      <Text>Тема вернётся к системной, а приложение снова покажет знакомство. Серверные данные останутся без изменений.</Text>
      <Stack mt="lg" gap="xs"><Button color="red" onClick={() => { setConfirmOpened(false); onReset(); }}>Сбросить</Button><Button variant="subtle" onClick={() => setConfirmOpened(false)}>Отмена</Button></Stack>
    </Modal>
  </Stack>;
}
