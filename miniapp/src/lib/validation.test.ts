import { describe, expect, it } from "vitest";
import { invalidTelegramUsername } from "./validation";

describe("invalidTelegramUsername", () => {
  it("accepts usernames and Telegram links", () => {
    expect(invalidTelegramUsername("@valid_name, https://t.me/other_user")).toBeNull();
  });

  it("returns the first invalid value", () => {
    expect(invalidTelegramUsername("@valid_name, @bad")).toBe("@bad");
  });
});
