/// <reference types="vite/client" />

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  close(): void;
  colorScheme: "light" | "dark";
  BackButton: TelegramWebAppButton;
  SettingsButton?: TelegramWebAppButton;
  HapticFeedback?: {
    impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
    selectionChanged(): void;
  };
  onEvent(event: "themeChanged", callback: () => void): void;
  offEvent(event: "themeChanged", callback: () => void): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  setBottomBarColor?(color: string): void;
}

interface TelegramWebAppButton {
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

interface Window {
  Telegram?: { WebApp: TelegramWebApp };
}
