import { Modal } from "@mantine/core";
import { AppearanceSettings } from "../components/AppearanceSettings";
import type { ThemePreference } from "../types";

export function AppSettingsModal({ opened, onClose, value, onChange, onReset }: {
  opened: boolean;
  onClose: () => void;
  value: ThemePreference;
  onChange: (value: ThemePreference) => void;
  onReset: () => void;
}) {
  return <Modal opened={opened} onClose={onClose} title="Настройки" fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    <div className="page-heading"><div className="eyebrow">Приложение</div><h1>Настройки</h1></div>
    <AppearanceSettings value={value} onChange={onChange} onReset={onReset} />
  </Modal>;
}
