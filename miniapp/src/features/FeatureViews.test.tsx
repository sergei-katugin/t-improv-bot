import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("ShowForm", () => {
  it("defaults registration closing to one hour before the show", () => {
    expect(oneHourBefore("2027-09-05T20:00")).toBe("2027-09-05T19:00");
    expect(newShowForm().maxGuests).toBe(6);
  });

  it("allows an editor to inspect every step", () => {
    render(<ShowForm opened initial={show} options={options} me={me} reloadOptions={async () => undefined} onClose={() => undefined} onSaved={() => undefined} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Шаг 2: Место" }));
    expect(screen.getByText("Открыть на карте ↗")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Шаг 3: Запись" }));
    expect(screen.getByText("Ответственный в Telegram")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Шаг 4: Афиша" }));
    expect(screen.getByText("Изображение афиши")).toBeInTheDocument();
  });

  it("saves an edited show after asking about notifications", async () => {
    history.replaceState({}, "", "/?preview=1");
    const onSaved = vi.fn();
    render(<ShowForm opened initial={show} options={options} me={me} reloadOptions={async () => undefined} onClose={vi.fn()} onSaved={onSaved} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Шаг 4: Афиша" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить изменения" }));
    fireEvent.click(await screen.findByRole("button", { name: "Сохранить без уведомления" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.any(Number)));
    history.replaceState({}, "", "/");
  });
});

describe("ManagementModal", () => {
  it("keeps root navigation on the administration overview", () => {
    const onCreate = vi.fn();
    const onSettings = vi.fn();
    render(<ManagementModal opened onClose={vi.fn()} onCreate={onCreate} onSettings={onSettings} me={me} options={options} reload={async () => undefined} themePreference="system" onThemePreferenceChange={vi.fn()} onResetLocalData={vi.fn()} backHandlerRef={createRef()} />, { wrapper });
    expect(screen.getByRole("button", { name: "Управление" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));
    fireEvent.click(screen.getByRole("button", { name: "Настройки" }));
    expect(onCreate).toHaveBeenCalledOnce();
    expect(onSettings).toHaveBeenCalledOnce();
  });

  it("opens administration sections", () => {
    render(<ManagementModal opened onClose={() => undefined} me={me} options={options} reload={async () => undefined} themePreference="system" onThemePreferenceChange={() => undefined} onResetLocalData={() => undefined} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Команды/ }));
    expect(screen.getByText("Экспериментаторы")).toBeInTheDocument();
  });

  it("opens venue editor and channel editor", async () => {
    const props = { opened: true, onClose: vi.fn(), me, options, reload: async () => undefined, themePreference: "system" as const, onThemePreferenceChange: vi.fn(), onResetLocalData: vi.fn(), backHandlerRef: createRef<(() => boolean) | null>() };
    const view = render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Площадки/ }));
    fireEvent.click(screen.getByRole("button", { name: /Добавить площадку/ }));
    expect(await screen.findByRole("heading", { name: "Новая площадка" })).toBeInTheDocument();
    view.unmount();

    render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Каналы для анонсов/ }));
    fireEvent.click(screen.getByRole("button", { name: /Добавить канал/ }));
    expect(await screen.findByText("Новый рекламный канал")).toBeInTheDocument();
  });

  it("shows access controls and the audit log", async () => {
    history.replaceState({}, "", "/?preview=1");
    render(<ManagementModal opened onClose={vi.fn()} me={me} options={options} reload={async () => undefined} themePreference="system" onThemePreferenceChange={vi.fn()} onResetLocalData={vi.fn()} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Доступ и журнал/ }));
    expect(await screen.findByText("@anna_impro")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Журнал действий" }));
    expect(await screen.findByText("Афиша опубликована")).toBeInTheDocument();
    history.replaceState({}, "", "/");
  });

  it("creates a team on its dedicated screen", async () => {
    history.replaceState({}, "", "/?preview=1");
    const reload = vi.fn(async () => undefined);
    render(<ManagementModal opened onClose={vi.fn()} me={me} options={options} reload={reload} themePreference="system" onThemePreferenceChange={vi.fn()} onResetLocalData={vi.fn()} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Команды/ }));
    fireEvent.click(screen.getByRole("button", { name: /Добавить команду/ }));
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Новая команда" } });
    fireEvent.change(screen.getByLabelText("Telegram-ники участников"), { target: { value: "@valid_user" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить команду" }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    history.replaceState({}, "", "/");
  });
});

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
});

describe("AttendeesModal", () => {
  it("shows viewers immediately as a simple list", () => {
    render(<AttendeesModal opened onClose={vi.fn()} show={show} demo backHandlerRef={createRef<(() => boolean) | null>()} onEdit={vi.fn()} onAnnouncement={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(screen.getByText("Анна Смирнова")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Фильтр зрителей"), { target: { value: "Анна" } });
    expect(screen.queryByRole("button", { name: "Отменить" })).not.toBeInTheDocument();
  });
});

describe("AnalyticsModal", () => {
  it("shows attendance, sources, feedback and demo export", async () => {
    render(<AnalyticsModal opened onClose={vi.fn()} show={show} demo onEdit={vi.fn()} onAnnouncement={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(await screen.findByText("10 / 80")).toBeInTheDocument();
    expect(screen.getByText("Через бота")).toBeInTheDocument();
    expect(screen.getByText("Очень тёплое и смешное шоу!")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Скачать отчёт · CSV" }));
    expect(screen.getByText("★ 4.7 · 18")).toBeInTheDocument();
  });
});

describe("AnnouncementModal", () => {
  it("renders publication controls and confirmation", async () => {
    render(<AnnouncementModal opened onClose={() => undefined} show={show} demo onEdit={() => undefined} onAnalytics={() => undefined} onRegistration={() => undefined} onMore={() => undefined} onPublished={() => undefined} />, { wrapper });
    expect(await screen.findByRole("button", { name: "Опубликовать в основном канале" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Опубликовать в основном канале" }));
    expect(await screen.findByText("Анонс уже публиковался. Если до шоу осталось мало времени и есть свободные места, его можно отправить повторно.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Опубликовать повторно" }));
    expect(await screen.findByText("Повторить публикацию?")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Да, отправить повторно" }));
    await waitFor(() => expect(screen.queryByText("Повторить публикацию?")).not.toBeInTheDocument());
  });

  it("sends a test announcement in preview mode", async () => {
    render(<AnnouncementModal opened onClose={vi.fn()} show={show} demo onEdit={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} onPublished={vi.fn()} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Отправить тест себе" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Отправить тест себе" })).not.toBeDisabled());
  });
});
