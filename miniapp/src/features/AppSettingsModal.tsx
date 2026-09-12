import { Modal } from "@mantine/core";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { RootNavigation } from "../components/BottomActionBar";
import type { ThemePreference } from "../types";

export function AppSettingsModal({ opened, onClose, onCreate, onAdministration, value, onChange, onReset }: {
  opened: boolean;
  onClose: () => void;
  onCreate?: () => void;
  onAdministration?: () => void;
  value: ThemePreference;
  onChange: (value: ThemePreference) => void;
  onReset: () => void;
}) {
  return <Modal opened={opened} onClose={onClose} title="Настройки" fullScreen classNames={{ close: "fullscreen-modal-close" }}>
    <AppearanceSettings value={value} onChange={onChange} onReset={onReset} />
    <RootNavigation active="settings" onShows={onClose} onCreate={onCreate ?? onClose} onAdministration={onAdministration ?? onClose} onSettings={() => undefined} />
  </Modal>;
}
