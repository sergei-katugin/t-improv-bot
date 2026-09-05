export function telegramHaptic(kind: "selection" | "light" = "selection") {
  const haptic = window.Telegram?.WebApp.HapticFeedback;
  if (kind === "selection") haptic?.selectionChanged();
  else haptic?.impactOccurred("light");
}

export function telegramConfirm(message: string): Promise<boolean> {
  const showConfirm = window.Telegram?.WebApp.showConfirm;
  if (showConfirm) {
    return new Promise((resolve) => showConfirm(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
}
