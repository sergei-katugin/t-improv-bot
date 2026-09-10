import { notifications, notificationsStore } from "@mantine/notifications";
import { afterEach, describe, expect, it } from "vitest";
import { NOTIFICATION_LIFETIME_MS, showNotification } from "./notifications";

describe("showNotification", () => {
  afterEach(() => notifications.clean());

  it("closes regular notifications after five seconds", () => {
    const id = showNotification({ color: "green", message: "Сохранено" });
    const item = notificationsStore.getState().notifications.find((entry) => entry.id === id);
    expect(item?.autoClose).toBe(NOTIFICATION_LIFETIME_MS);
  });

  it("keeps errors visible until the user closes them", () => {
    const id = showNotification({ color: "red", message: "Ошибка" });
    const item = notificationsStore.getState().notifications.find((entry) => entry.id === id);
    expect(item?.autoClose).toBe(false);
    expect(item?.allowClose).not.toBe(false);
  });
});
