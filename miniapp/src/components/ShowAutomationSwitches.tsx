import { ActionIcon, Group, Popover, Stack, Switch, Text } from "@mantine/core";


function AutomationSwitch({ label, description, checked, onChange }: {
  label: string; description: string; checked: boolean; onChange: (checked: boolean) => void;
}) {
  return <Group className="automation-switch" justify="space-between" wrap="nowrap">
    <Switch label={label} checked={checked} onChange={(event) => onChange(event.currentTarget.checked)} />
    <Popover width={260} position="top-end" withArrow shadow="md">
      <Popover.Target>
        <ActionIcon variant="subtle" color="gray" radius="xl" aria-label={`Что означает «${label}»`}>
          <span className="info-icon">i</span>
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown><Text size="sm">{description}</Text></Popover.Dropdown>
    </Popover>
  </Group>;
}


export function ShowAutomationSwitches({ feedbackEnabled, checkinEnabled, onFeedbackChange, onCheckinChange }: {
  feedbackEnabled: boolean; checkinEnabled: boolean;
  onFeedbackChange: (checked: boolean) => void;
  onCheckinChange: (checked: boolean) => void;
}) {
  return <Stack className="automation-switches" gap="xs">
    <AutomationSwitch
      label="Запрашивать отзывы после шоу"
      description="После завершения шоу бот попросит пришедших поставить оценку. Текстовый комментарий можно оставить по желанию."
      checked={feedbackEnabled}
      onChange={onFeedbackChange}
    />
  </Stack>;
}
