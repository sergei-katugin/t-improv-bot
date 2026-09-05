import React from "react";
import { Button, Modal, Stack, Text, Title } from "@mantine/core";
import { BottomActionBar } from "./BottomActionBar";

const steps = [
  {
    eyebrow: "Для организаторов",
    title: "Создавай афиши и управляй шоу",
    text: "Создай афишу — дальше бот сам запишет зрителей и заранее напомнит им о шоу. Тебе не придётся вести списки и рассылать уведомления вручную.",
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

function OnboardingIllustration({ step }: { step: number }) {
  return <div className="onboarding-illustration" aria-hidden="true">
    <svg viewBox="0 0 320 180">
      {step === 0 && <>
        <rect className="illustration-surface" x="38" y="22" width="244" height="136" rx="18" />
        <rect className="illustration-line" x="58" y="43" width="82" height="9" rx="4.5" />
        <rect className="illustration-card" x="58" y="70" width="204" height="65" rx="12" />
        <path d="M76 89h82M76 104h124M76 119h105" />
        <circle className="illustration-accent" cx="237" cy="91" r="9" />
      </>}
      {step === 1 && <>
        <rect className="illustration-surface" x="64" y="18" width="192" height="144" rx="18" />
        <circle className="illustration-accent" cx="96" cy="47" r="13" /><path d="M126 47h98" />
        <circle className="illustration-card" cx="96" cy="86" r="13" /><path d="M126 86h76" />
        <circle className="illustration-card" cx="96" cy="125" r="13" /><path d="M126 125h91" />
        <path className="illustration-number" d="M96 42v10M91 47h10" />
      </>}
      {step === 2 && <>
        <path className="illustration-surface" d="M48 31h224a16 16 0 0 1 16 16v84a16 16 0 0 1-16 16H139l-31 20 5-20H48a16 16 0 0 1-16-16V47a16 16 0 0 1 16-16Z" />
        <circle className="illustration-accent" cx="70" cy="70" r="17" />
        <path d="M99 61h117M99 78h82M58 111h183" />
        <rect className="illustration-card" x="198" y="99" width="60" height="25" rx="12.5" />
        <path className="illustration-number" d="M218 111h20M228 101v20" />
      </>}
      {step === 3 && <>
        <rect className="illustration-surface" x="35" y="29" width="250" height="122" rx="18" />
        <path d="M57 125V91M91 125V66M125 125v-19M159 125V79" />
        <path className="illustration-accent-stroke" d="m190 102 20 20 51-56" />
        <path d="M57 125h111" />
      </>}
    </svg>
  </div>;
}

export function MiniAppOnboarding({ opened, onFinish }: { opened: boolean; onFinish: () => void }) {
  const [step, setStep] = React.useState(0);
  const touchStart = React.useRef<{ x: number; y: number } | null>(null);
  React.useEffect(() => { if (opened) setStep(0); }, [opened]);
  const current = steps[step];

  function finishSwipe(x: number, y: number) {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start) return;
    const deltaX = x - start.x;
    const deltaY = y - start.y;
    if (Math.abs(deltaX) < 44 || Math.abs(deltaX) <= Math.abs(deltaY) * 1.2) return;
    if (deltaX < 0 && step < steps.length - 1) setStep((value) => value + 1);
    if (deltaX > 0 && step > 0) setStep((value) => value - 1);
  }

  return <Modal opened={opened} onClose={onFinish} fullScreen withCloseButton={false}>
    <div
      className="onboarding-screen"
      onTouchStart={(event) => {
        const touch = event.changedTouches[0];
        if (touch) touchStart.current = { x: touch.clientX, y: touch.clientY };
      }}
      onTouchEnd={(event) => {
        const touch = event.changedTouches[0];
        if (touch) finishSwipe(touch.clientX, touch.clientY);
      }}
      onTouchCancel={() => { touchStart.current = null; }}
    >
      <div className="onboarding-content">
        <OnboardingIllustration step={step} />
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
          <div className="onboarding-secondary-actions">
            {step < steps.length - 1 && <Button variant="subtle" onClick={onFinish}>Пропустить знакомство</Button>}
          </div>
        </Stack>
      </BottomActionBar>
    </div>
  </Modal>;
}
