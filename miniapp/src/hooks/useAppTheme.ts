import React from "react";
import type { ThemePreference } from "../types";

function toHexColor(value: string): string | null {
  if (/^#[0-9a-f]{6}$/i.test(value)) return value;
  const channels = value.match(/^rgba?\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)/i);
  if (!channels) return null;
  return `#${channels.slice(1, 4).map((channel) => Number(channel).toString(16).padStart(2, "0")).join("")}`;
}

export function useAppTheme() {
  const telegram = window.Telegram?.WebApp;
  const [preference, setPreference] = React.useState<ThemePreference>(() => {
    const stored = localStorage.getItem("miniapp-theme");
    return stored === "light" || stored === "dark" ? stored : "system";
  });
  const resolve = React.useCallback((): "light" | "dark" => {
    if (preference !== "system") return preference;
    return telegram?.colorScheme ?? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  }, [preference, telegram]);
  const [colorScheme, setColorScheme] = React.useState<"light" | "dark">(resolve);

  const changePreference = React.useCallback((next: ThemePreference) => {
    setPreference(next);
    if (next === "system") localStorage.removeItem("miniapp-theme");
    else localStorage.setItem("miniapp-theme", next);
  }, []);

  React.useEffect(() => {
    const sync = () => {
      const next = resolve();
      setColorScheme(next);
      document.documentElement.dataset.theme = next;
      // Read the resolved color instead of passing `var(--app-bg)` to Telegram.
      // Android recreates the native WebView backdrop after resume and otherwise
      // falls back to black even while the document itself remains in light mode.
      const background = toHexColor(getComputedStyle(document.body).backgroundColor);
      if (background) {
        document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute("content", background);
        telegram?.setHeaderColor(background);
        telegram?.setBackgroundColor(background);
        telegram?.setBottomBarColor?.(background);
      }
    };
    const onVisibilityChange = () => { if (document.visibilityState === "visible") sync(); };
    const systemTheme = window.matchMedia("(prefers-color-scheme: light)");
    if (telegram?.initData) document.documentElement.dataset.telegram = "true";
    sync();
    telegram?.onEvent("themeChanged", sync);
    telegram?.onEvent("activated", sync);
    systemTheme.addEventListener("change", sync);
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pageshow", sync);
    window.addEventListener("focus", sync);
    telegram?.ready();
    telegram?.expand();
    return () => {
      telegram?.offEvent("themeChanged", sync);
      telegram?.offEvent("activated", sync);
      systemTheme.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pageshow", sync);
      window.removeEventListener("focus", sync);
    };
  }, [resolve, telegram]);

  return { colorScheme, preference, changePreference };
}
