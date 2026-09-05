import React from "react";
import { Button, Modal, Stack, Text, Title } from "@mantine/core";
import { BottomActionBar } from "./BottomActionBar";

const steps = [
  {
    eyebrow: "Афиши",
    title: "Все шоу в одном месте",
    text: "Смотри будущие и прошедшие афиши, фильтруй их по команде и году, а также сразу видь заполняемость.",
  },
  {
    eyebrow: "Создание",
    title: "Новая афиша за четыре шага",
    text: "Выбери команду, площадку и дату, настрой запись, проверь превью и опубликуй анонс.",
  },
  {
    eyebrow: "Записи",
    title: "Рабочий чат без лишних действий",
    text: "Добавь админ-бота в группу или канал. Новые записи придут туда, а зрителя из другой соцсети можно добавить прямо в чате.",
  },
  {
    eyebrow: "Управление",
    title: "Всё готово к работе",
    text: "Открой афишу, чтобы увидеть зрителей, анонс, аналитику и другие действия. В настройках можно изменить тему и заново запустить это знакомство.",
  },
] as const;

export function MiniAppOnboarding({ opened, onFinish }: { opened: boolean; onFinish: () => void }) {
  const [step, setStep] = React.useState(0);
  React.useEffect(() => { if (opened) setStep(0); }, [opened]);
  const current = steps[step];

  return <Modal opened={opened} onClose={onFinish} fullScreen withCloseButton={false}>
    <div className="onboarding-screen">
      <button type="button" className="onboarding-skip" onClick={onFinish}>Пропустить</button>
      <div className="onboarding-content">
        <Text className="onboarding-eyebrow">{current.eyebrow}</Text>
        <Title order={1}>{current.title}</Title>
        <Text className="onboarding-copy">{current.text}</Text>
      </div>
      <div className="onboarding-progress" aria-label={`Шаг ${step + 1} из ${steps.length}`}>
        {steps.map((item, index) => <span key={item.eyebrow} data-active={index === step} data-complete={index < step} />)}
      </div>
      <BottomActionBar>
        <Stack gap="xs">
          <Button className="primary" fullWidth onClick={() => step === steps.length - 1 ? onFinish() : setStep((value) => value + 1)}>{step === steps.length - 1 ? "Начать" : "Дальше"}</Button>
          {step > 0 && <Button variant="subtle" fullWidth onClick={() => setStep((value) => value - 1)}>Назад</Button>}
        </Stack>
      </BottomActionBar>
    </div>
  </Modal>;
}
