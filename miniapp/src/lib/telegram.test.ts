import { afterEach, describe, expect, it, vi } from "vitest";
import { telegramConfirm, telegramHaptic } from "./telegram";

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
});
