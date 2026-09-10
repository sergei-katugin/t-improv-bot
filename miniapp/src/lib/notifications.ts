import { notifications, type NotificationData } from "@mantine/notifications";

export const NOTIFICATION_LIFETIME_MS = 5_000;

export function showNotification(notification: NotificationData) {
  return notifications.show({
    ...notification,
    autoClose: notification.color === "red" ? false : NOTIFICATION_LIFETIME_MS,
  });
}
