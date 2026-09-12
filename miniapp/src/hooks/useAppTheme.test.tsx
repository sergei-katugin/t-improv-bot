import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { applyTelegramTheme } from "../lib/telegramTheme";
import { useAppTheme } from "./useAppTheme";

afterEach(() => {
  delete window.Telegram;
  localStorage.removeItem("miniapp-theme");
  applyTelegramTheme(undefined);
});

it("reapplies Telegram colors on resume and clears them for a manual theme", () => {
  localStorage.removeItem("miniapp-theme");
  const events = new Map<string, () => void>();
  const webApp = {
    initData: "signed", colorScheme: "light", themeParams: { bg_color: "#123456", text_color: "#abcdef" },
    ready: vi.fn(), expand: vi.fn(), setHeaderColor: vi.fn(), setBackgroundColor: vi.fn(),
    onEvent: (event: string, callback: () => void) => events.set(event, callback), offEvent: vi.fn(),
  };
  window.Telegram = { WebApp: webApp } as unknown as typeof window.Telegram;
  const { result } = renderHook(useAppTheme);
  expect(result.current.colorScheme).toBe("light");
  expect(document.documentElement.style.getPropertyValue("--app-bg")).toBe("#123456");
  webApp.themeParams.bg_color = "#234567";
  act(() => events.get("activated")?.());
  expect(document.documentElement.style.getPropertyValue("--app-bg")).toBe("#234567");
  act(() => result.current.changePreference("dark"));
  expect(result.current.colorScheme).toBe("dark");
  expect(document.documentElement.style.getPropertyValue("--app-bg")).toBe("");
  expect(localStorage.getItem("miniapp-theme")).toBe("dark");
});
