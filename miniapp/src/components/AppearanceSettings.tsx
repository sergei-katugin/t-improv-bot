import { Paper, SegmentedControl, Stack, Text, Title } from "@mantine/core";
import type { ThemePreference } from "../types";

export function AppearanceSettings({ value, onChange }: { value: ThemePreference; onChange: (value: ThemePreference) => void }) {
  return <Paper className="resource-form">
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
  </Paper>;
}
