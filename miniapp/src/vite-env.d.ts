/// <reference types="vite/client" />

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  close(): void;
  colorScheme: "light" | "dark";
}

interface Window {
  Telegram?: { WebApp: TelegramWebApp };
}
