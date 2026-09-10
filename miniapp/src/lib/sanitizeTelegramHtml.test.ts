import { describe, expect, it } from "vitest";
import { sanitizeTelegramHtml } from "./sanitizeTelegramHtml";

describe("sanitizeTelegramHtml", () => {
  it("preserves Telegram formatting and safe links", () => {
    const result = sanitizeTelegramHtml('<b>Шоу</b><br><a href="https://t.me/test">ссылка</a>');
    expect(result).toContain("<b>Шоу</b><br>");
    expect(result).toContain('href="https://t.me/test"');
    expect(result).toContain('rel="noopener noreferrer"');
  });

  it("removes scripts, event handlers and unsafe link protocols", () => {
    const result = sanitizeTelegramHtml(
      '<script>alert(1)</script><b onclick="alert(2)">Текст</b><a href="javascript:alert(3)">опасно</a>',
    );
    expect(result).not.toContain("script");
    expect(result).not.toContain("onclick");
    expect(result).not.toContain("javascript:");
    expect(result).toContain("<b>Текст</b>");
    expect(result).toContain("<a>опасно</a>");
  });
});
