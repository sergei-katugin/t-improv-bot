import { afterEach, describe, expect, it, vi } from "vitest";
import { openTelegramLink, telegramConfirm, telegramHaptic } from "./telegram";

describe("Telegram helpers", () => {
  afterEach(() => Object.defineProperty(window, "Telegram", { configurable: true, value: undefined }));

  it("uses Telegram haptic feedback when available", () => {
    const selectionChanged = vi.fn();
    const impactOccurred = vi.fn();
    Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: { HapticFeedback: { selectionChanged, impactOccurred } } } });
    telegramHaptic();
    telegramHaptic("light");
    expect(selectionChanged).toHaveBeenCalledOnce();
    expect(impactOccurred).toHaveBeenCalledWith("light");
  });

  it("uses Telegram confirmation and falls back to the browser", async () => {
    const showConfirm = vi.fn((_message: string, resolve: (confirmed: boolean) => void) => resolve(true));
    Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: { showConfirm } } });
    await expect(telegramConfirm("Удалить?")).resolves.toBe(true);
    expect(showConfirm).toHaveBeenCalledWith("Удалить?", expect.any(Function));

    Object.defineProperty(window, "Telegram", { configurable: true, value: undefined });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await expect(telegramConfirm("Удалить?")).resolves.toBe(false);
  });

  it("opens Telegram links through the Mini App API with a browser fallback", () => {
    const nativeOpen = vi.fn();
    Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: { openTelegramLink: nativeOpen } } });
    openTelegramLink("https://t.me/sergey_katugin");
    expect(nativeOpen).toHaveBeenCalledWith("https://t.me/sergey_katugin");

    Object.defineProperty(window, "Telegram", { configurable: true, value: undefined });
    const browserOpen = vi.spyOn(window, "open").mockImplementation(() => null);
    openTelegramLink("https://t.me/sergey_katugin");
    expect(browserOpen).toHaveBeenCalledWith("https://t.me/sergey_katugin", "_blank", "noopener,noreferrer");
  });
});
