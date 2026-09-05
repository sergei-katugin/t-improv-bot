export function telegramHaptic(kind: "selection" | "light" = "selection") {
  const haptic = window.Telegram?.WebApp.HapticFeedback;
  if (kind === "selection") haptic?.selectionChanged();
  else haptic?.impactOccurred("light");
}
