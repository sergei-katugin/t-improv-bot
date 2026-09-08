import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createRef, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Me, Options, Show } from "../types";
import { AnnouncementModal } from "./AnnouncementModal";
import { AttendeesModal } from "./AttendeesModal";
import { AnalyticsModal } from "../components/AnalyticsModal";
import { ManagementModal } from "./ManagementModal";
import { newShowForm, oneHourBefore, ShowForm } from "./ShowForm";
import { ShowToolsModal } from "./ShowToolsModal";

const wrapper = ({ children }: { children: ReactNode }) => <MantineProvider>{children}</MantineProvider>;
const show = { id: 1, title: "Супер", teamName: "Экспериментаторы", showDateLabel: "5 сентября, 20:00", showDateLocal: "2027-09-05T20:00", location: "Театр", city: "Лимасол", occupiedSeats: 10, maxSeats: 80, isActive: true, isPast: false, registrarUsername: "sergey", posterText: "Описание", hasPublished: true } as Show;
const options: Options = {
  teams: [{ id: 1, name: "Экспериментаторы", members: "@sergey" }],
  venues: [{ id: 1, name: "Театр", city: "Лимасол", mapsUrl: "https://example.com", defaultSeats: 80 }],
  adChannels: [{ id: 1, username: "events", isActive: true }],
};
const me: Me = { id: 1, firstName: "Sergey", username: "sergey", role: "admin" };


describe("ShowToolsModal", () => {
  it("keeps a published announcement in more actions", () => {
    const onClose = vi.fn();
    const onAnnouncement = vi.fn();
    const props = { mode: "all" as const, opened: true, onClose, show, registrationUrl: "https://t.me/test", demo: true, backHandlerRef: createRef<(() => boolean) | null>(), onEdit: vi.fn(), onAnalytics: vi.fn(), onAnnouncement, onChanged: vi.fn(), onDeleted: vi.fn() };
    render(<ShowToolsModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Анонс/ }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(onAnnouncement).toHaveBeenCalledOnce();
  });

  it("does not duplicate analytics for a past show", () => {
    const props = { mode: "all" as const, opened: true, onClose: vi.fn(), show: { ...show, isPast: true }, registrationUrl: "https://t.me/test", demo: true, backHandlerRef: createRef<(() => boolean) | null>(), onEdit: vi.fn(), onAnalytics: vi.fn(), onAnnouncement: vi.fn(), onChanged: vi.fn(), onDeleted: vi.fn() };
    render(<ShowToolsModal {...props} />, { wrapper });
    expect(screen.getByRole("dialog", { name: "Настройки · Супер" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Аналитика" })).toHaveLength(1);
  });

  it("opens registration and clone tools", async () => {
    const props = { mode: "all" as const, opened: true, onClose: vi.fn(), show, registrationUrl: "https://t.me/test", demo: true, backHandlerRef: createRef<(() => boolean) | null>(), onEdit: vi.fn(), onAnalytics: vi.fn(), onAnnouncement: vi.fn(), onChanged: vi.fn(), onDeleted: vi.fn() };
    render(<ShowToolsModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Ссылка и QR/ }));
    expect(screen.getByText("https://t.me/test")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Скачать QR" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Скачать QR" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Все действия/ }));
    fireEvent.click(screen.getByRole("button", { name: /Создать копию/ }));
    expect(screen.getByText("Дата и время новой афиши")).toBeInTheDocument();
  });

  it("confirms cancellation and restores an inactive show", async () => {
    const onChanged = vi.fn();
    const common = { mode: "all" as const, opened: true, onClose: vi.fn(), registrationUrl: "https://t.me/test", demo: true, backHandlerRef: createRef<(() => boolean) | null>(), onEdit: vi.fn(), onAnalytics: vi.fn(), onAnnouncement: vi.fn(), onChanged, onDeleted: vi.fn() };
    const view = render(<ShowToolsModal {...common} show={show} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Отменить афишу/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Да, отменить" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ isActive: false })));
    view.unmount();

    render(<ShowToolsModal {...common} show={{ ...show, isActive: false }} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Восстановить афишу/ }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ isActive: true })));
  });

  it("clones and permanently deletes a past show", async () => {
    history.replaceState({}, "", "/?preview=1");
    const onClose = vi.fn();
    const onDeleted = vi.fn();
    const common = { mode: "all" as const, opened: true, onClose, registrationUrl: "https://t.me/test", demo: true, backHandlerRef: createRef<(() => boolean) | null>(), onEdit: vi.fn(), onAnalytics: vi.fn(), onAnnouncement: vi.fn(), onChanged: vi.fn(), onDeleted };
    const view = render(<ShowToolsModal {...common} show={show} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Создать копию/ }));
    fireEvent.click(screen.getByRole("button", { name: "Создать копию" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    view.unmount();

    render(<ShowToolsModal {...common} show={{ ...show, isPast: true }} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Удалить навсегда/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Удалить навсегда" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    history.replaceState({}, "", "/");
  });

  it("disconnects an attached registration chat after confirmation", async () => {
    history.replaceState({}, "", "/?preview=1");
    const onChanged = vi.fn();
    const attached = { ...show, registrationChatId: -1001, registrationChatTitle: "Записи" };
    render(<ShowToolsModal mode="chat" opened onClose={vi.fn()} show={attached} registrationUrl="https://t.me/test" demo={false} backHandlerRef={createRef()} onEdit={vi.fn()} onAnalytics={vi.fn()} onAnnouncement={vi.fn()} onChanged={onChanged} onDeleted={vi.fn()} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Отключить чат" }));
    fireEvent.click(await screen.findByRole("button", { name: "Отключить" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ registrationChatId: null })));
    history.replaceState({}, "", "/");
  });

  it("routes actionable warnings to edit, announcement and chat", async () => {
    const onEdit = vi.fn();
    const onAnnouncement = vi.fn();
    const onClose = vi.fn();
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = String(input);
      const body = path.includes("/tasks") ? { items: [
        { key: "announcement", label: "Сделать анонс", count: 1 },
        { key: "show_responsible", label: "Назначить ответственного", count: 1 },
        { key: "registration_chat", label: "Подключить чат", count: 1 },
      ] } : { items: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const props = { mode: "all" as const, opened: true, onClose, show, registrationUrl: "https://t.me/test", demo: false, backHandlerRef: createRef<(() => boolean) | null>(), onEdit, onAnalytics: vi.fn(), onAnnouncement, onChanged: vi.fn(), onDeleted: vi.fn() };
    const first = render(<ShowToolsModal {...props} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /Сделать анонс/ }));
    expect(onAnnouncement).toHaveBeenCalled();
    first.unmount();
    const second = render(<ShowToolsModal {...props} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /Назначить ответственного/ }));
    expect(onEdit).toHaveBeenCalled();
    second.unmount();
    render(<ShowToolsModal {...props} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /Подключить чат/ }));
    expect(await screen.findByText("Сюда бот будет отправлять сообщения о новых записях.")).toBeInTheDocument();
    fetchMock.mockRestore();
    delete window.Telegram;
  });

  it("copies the registration link and handles nested back navigation", async () => {
    const clipboard = { writeText: vi.fn(async () => undefined) };
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
    const backHandlerRef = createRef<(() => boolean) | null>();
    render(<ShowToolsModal mode="all" opened onClose={vi.fn()} show={show} registrationUrl="https://t.me/test" demo backHandlerRef={backHandlerRef} onEdit={vi.fn()} onAnalytics={vi.fn()} onAnnouncement={vi.fn()} onChanged={vi.fn()} onDeleted={vi.fn()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Ссылка и QR/ }));
    fireEvent.click(screen.getByRole("button", { name: "Копировать" }));
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalledWith("https://t.me/test"));
    expect(backHandlerRef.current?.()).toBe(true);
    await waitFor(() => expect(screen.getByRole("button", { name: /Создать копию/ })).toBeInTheDocument());
  });

  it("confirms that manual contacts were notified", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = String(input);
      const body = path.includes("manual-notifications/confirm") ? { confirmed: 2 } : path.includes("/tasks")
        ? { items: [{ key: "manual_notifications", label: "Уведомить вручную", count: 2 }] }
        : { items: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(<ShowToolsModal mode="all" opened onClose={vi.fn()} show={show} registrationUrl="https://t.me/test" demo={false} backHandlerRef={createRef()} onEdit={vi.fn()} onAnalytics={vi.fn()} onAnnouncement={vi.fn()} onChanged={vi.fn()} onDeleted={vi.fn()} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: /Уведомить вручную/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Уведомить вручную/ })).not.toBeInTheDocument());
    fetchMock.mockRestore();
    delete window.Telegram;
  });
});
