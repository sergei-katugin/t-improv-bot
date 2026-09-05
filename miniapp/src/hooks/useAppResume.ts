import React from "react";

export function useAppResume(callback: () => void, enabled = true) {
  const callbackRef = React.useRef(callback);
  callbackRef.current = callback;

  React.useEffect(() => {
    if (!enabled) return;
    let lastRefresh = 0;
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      const now = Date.now();
      if (now - lastRefresh < 750) return;
      lastRefresh = now;
      callbackRef.current();
    };
    const onVisibilityChange = () => { if (document.visibilityState === "visible") refresh(); };
    const telegram = window.Telegram?.WebApp;
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    telegram?.onEvent("activated", refresh);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      telegram?.offEvent("activated", refresh);
    };
  }, [enabled]);
}
