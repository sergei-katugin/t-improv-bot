import React from "react";
import type { ThemePreference } from "../types";

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
      const background = getComputedStyle(document.documentElement).getPropertyValue("--app-bg").trim();
      telegram?.setHeaderColor(background);
      telegram?.setBackgroundColor(background);
      telegram?.setBottomBarColor?.(background);
    };
    const systemTheme = window.matchMedia("(prefers-color-scheme: light)");
    if (telegram?.initData) document.documentElement.dataset.telegram = "true";
    sync();
    telegram?.onEvent("themeChanged", sync);
    systemTheme.addEventListener("change", sync);
    telegram?.ready();
    telegram?.expand();
    return () => { telegram?.offEvent("themeChanged", sync); systemTheme.removeEventListener("change", sync); };
  }, [resolve, telegram]);

  return { colorScheme, preference, changePreference };
}
