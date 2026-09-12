import { afterEach, describe, expect, it } from "vitest";
import { applyTelegramTheme } from "./telegramTheme";

describe("Telegram theme tokens", () => {
  afterEach(() => applyTelegramTheme(undefined));
  it("maps custom Telegram colors and falls back for older clients", () => {
    applyTelegramTheme({ bg_color: "#123456", text_color: "#abcdef", secondary_bg_color: "#234567", button_color: "#345678", hint_color: "#456789" });
    const style = document.documentElement.style;
    expect(style.getPropertyValue("--app-bg")).toBe("#123456");
    expect(style.getPropertyValue("--surface")).toBe("#234567");
    expect(style.getPropertyValue("--accent")).toBe("#345678");
    expect(style.getPropertyValue("--muted")).toBe("#456789");
  });
  it("removes stale colors on manual theme selection and rejects malformed values", () => {
    applyTelegramTheme({ bg_color: "#123456" });
    applyTelegramTheme({ bg_color: "url(unsafe)", section_bg_color: "#abcdef" });
    expect(document.documentElement.style.getPropertyValue("--app-bg")).toBe("");
    applyTelegramTheme(undefined);
    expect(document.documentElement.style.getPropertyValue("--surface")).toBe("");
    expect(document.documentElement.style.getPropertyValue("--surface-strong")).toBe("");
  });
});
