import { useEffect } from "react";

/** Keep fixed actions above the keyboard without treating browser chrome as a keyboard. */
export function useKeyboardViewport() {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const root = document.documentElement;
    const sync = () => {
      const editing = document.activeElement?.matches("input, textarea, [contenteditable='true']");
      const inset = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      const opened = Boolean(editing && inset > 120 && viewport.scale === 1);
      root.dataset.keyboard = opened ? "open" : "closed";
      root.style.setProperty("--keyboard-inset", `${opened ? inset : 0}px`);
    };
    viewport.addEventListener("resize", sync);
    viewport.addEventListener("scroll", sync);
    document.addEventListener("focusin", sync);
    document.addEventListener("focusout", sync);
    window.addEventListener("pageshow", sync);
    sync();
    return () => {
      viewport.removeEventListener("resize", sync);
      viewport.removeEventListener("scroll", sync);
      document.removeEventListener("focusin", sync);
      document.removeEventListener("focusout", sync);
      window.removeEventListener("pageshow", sync);
      delete root.dataset.keyboard;
      root.style.removeProperty("--keyboard-inset");
    };
  }, []);
}
