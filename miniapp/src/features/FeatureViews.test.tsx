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

  it("edits custom venue, registration controls and poster preview", async () => {
    history.replaceState({}, "", "/?preview=1");
    const custom = { ...show, location: "Двор", city: "Пафос", locationUrl: "", maxGuests: 3, checkinEnabled: false, feedbackEnabled: false };
    const onSaved = vi.fn();
    render(<ShowForm opened initial={custom} options={options} me={me} reloadOptions={async () => undefined} onClose={vi.fn()} onSaved={onSaved} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Шаг 2: Место" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Название площадки/ }), { target: { value: "Новый двор" } });
    fireEvent.change(screen.getByRole("combobox", { name: /Город/ }), { target: { value: "Никосия" } });
    fireEvent.change(screen.getByRole("textbox", { name: /Ссылка на карту/ }), { target: { value: "https://maps.example/yard" } });
    fireEvent.click(screen.getByRole("button", { name: "Шаг 3: Запись" }));
    const registrar = screen.getByRole("combobox", { name: /Ответственный/ });
    fireEvent.change(registrar, { target: { value: "new_admin" } });
    fireEvent.blur(registrar);
    fireEvent.change(screen.getByLabelText("Максимум дополнительных гостей"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Шаг 4: Афиша" }));
    fireEvent.change(screen.getByLabelText("Текст афиши"), { target: { value: "Обновлённый текст" } });
    fireEvent.click(screen.getByLabelText("Включить check-in"));
    fireEvent.click(screen.getByLabelText("Запрашивать отзывы после шоу"));
    fireEvent.click(screen.getByRole("button", { name: "Показать предпросмотр" }));
    expect(screen.getAllByText("Обновлённый текст").length).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить изменения" }));
    fireEvent.click(await screen.findByRole("button", { name: "Сохранить и уведомить" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    history.replaceState({}, "", "/");
  });

  it("validates the first creation step and advances to the venue", async () => {
    history.replaceState({}, "", "/?preview=1");
    const onSaved = vi.fn();
    render(<ShowForm opened initial={null} options={options} me={me} reloadOptions={async () => undefined} onClose={vi.fn()} onSaved={onSaved} />, { wrapper });
    fireEvent.change(await screen.findByRole("textbox", { name: /Название/ }), { target: { value: "Премьера" } });
    const team = screen.getByRole("combobox", { name: /Команда/ });
    fireEvent.change(team, { target: { value: "Экспериментаторы" } });
    fireEvent.keyDown(team, { key: "ArrowDown" });
    fireEvent.keyDown(team, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "Далее" }));
    expect(screen.getByRole("combobox", { name: /Площадка/ })).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    history.replaceState({}, "", "/");
  });

  it("creates and selects a team from the form", async () => {
    history.replaceState({}, "", "/?preview=1");
    const reloadOptions = vi.fn(async () => undefined);
    render(<ShowForm opened initial={null} options={options} me={me} reloadOptions={reloadOptions} onClose={vi.fn()} onSaved={vi.fn()} />, { wrapper });
    const team = await screen.findByRole("combobox", { name: /Команда/ });
    fireEvent.change(team, { target: { value: "＋ Добавить новую команду" } });
    fireEvent.keyDown(team, { key: "ArrowDown" });
    fireEvent.keyDown(team, { key: "Enter" });
    const teamDialog = await screen.findByRole("dialog", { name: "Новая команда" });
    fireEvent.change(within(teamDialog).getByRole("textbox", { name: /Название/ }), { target: { value: "Другая команда" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать и выбрать" }));
    await waitFor(() => expect(reloadOptions).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Новая команда" })).not.toBeInTheDocument());
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

  it("edits existing team and venue records", async () => {
    history.replaceState({}, "", "/?preview=1");
    const reload = vi.fn(async () => undefined);
    const props = { opened: true, onClose: vi.fn(), me, options, reload, themePreference: "system" as const, onThemePreferenceChange: vi.fn(), onResetLocalData: vi.fn(), backHandlerRef: createRef<(() => boolean) | null>() };
    const teamView = render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Команды/ }));
    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Название/ }), { target: { value: "Экспериментаторы 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    teamView.unmount();

    render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Площадки/ }));
    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    fireEvent.change(screen.getByRole("textbox", { name: /Название/ }), { target: { value: "Театр 2" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Ссылка на карту" }), { target: { value: "https://maps.example/new" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(2));
    history.replaceState({}, "", "/");
  });

  it("creates an access invite, copies it and confirms revocation", async () => {
    history.replaceState({}, "", "/?preview=1");
    const clipboard = { writeText: vi.fn(async () => undefined) };
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
    render(<ManagementModal opened onClose={vi.fn()} me={me} options={options} reload={async () => undefined} themePreference="system" onThemePreferenceChange={vi.fn()} onResetLocalData={vi.fn()} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Доступ и журнал/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Пригласить организатора/ }));
    expect(await screen.findByText(/inv_demo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Копировать приглашение" }));
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Отозвать" }));
    expect(await screen.findByRole("dialog", { name: "Отозвать доступ?" })).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("dialog", { name: "Отозвать доступ?" })).getByRole("button", { name: "Отозвать" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Отозвать доступ?" })).not.toBeInTheDocument());
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

describe("AttendeesModal", () => {
  it("shows viewers immediately as a simple list", () => {
    render(<AttendeesModal opened onClose={vi.fn()} show={show} demo backHandlerRef={createRef<(() => boolean) | null>()} onEdit={vi.fn()} onAnnouncement={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(screen.getByText("Анна Смирнова")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Фильтр зрителей"), { target: { value: "Анна" } });
    expect(screen.queryByRole("button", { name: "Отменить" })).not.toBeInTheDocument();
  });

  it("loads and appends viewers from the API", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const second = String(input).includes("offset=100");
      const payload = { occupied: second ? 2 : 1, maxSeats: 20, arrived: 0, hasMore: !second, nextOffset: 100,
        registrations: [{ id: second ? 2 : 1, name: second ? "Борис" : "Анна", guests: 0, confirmed: null, checkedInCount: 0, source: "telegram" }], manual: [], waitlist: [] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(<AttendeesModal opened onClose={vi.fn()} show={show} demo={false} backHandlerRef={createRef()} onEdit={vi.fn()} onAnnouncement={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(await screen.findByText("Анна")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText("Борис")).toBeInTheDocument();
    expect(screen.getByText("Анна")).toBeInTheDocument();
    fetchMock.mockRestore(); delete window.Telegram;
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

  it("loads live analytics and exports CSV", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const payload = { registered: 0, capacity: 20, cancelledRegistrations: 1, confirmed: 0, arrived: 0, checkinEnabled: false, feedbackEnabled: false, feedbackCount: 0, averageRating: 0, ratingDistribution: {}, occupancyRate: 0, cancellationRate: 0, attendanceRate: 0, dailyRegistrationRate: 0, projectedAttendance: 0, recommendation: "Нужен анонс", sources: [], comments: [], commentsLimit: 100 };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).includes("export.csv")
      ? new Response("name", { status: 200 })
      : new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }));
    const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    const revokeUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const linkClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<AnalyticsModal opened onClose={vi.fn()} show={show} demo={false} onEdit={vi.fn()} onAnnouncement={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(await screen.findByText("Нужен анонс")).toBeInTheDocument();
    expect(screen.getByText("Данных пока нет")).toBeInTheDocument();
    expect(screen.getByText("Текстовых отзывов пока нет.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Скачать отчёт · CSV" }));
    await waitFor(() => expect(createUrl).toHaveBeenCalled());
    expect(revokeUrl).toHaveBeenCalledWith("blob:test");
    fetchMock.mockResolvedValue(new Response("", { status: 500, headers: { "X-Request-ID": "export-failed" } }));
    fireEvent.click(screen.getByRole("button", { name: "Скачать отчёт · CSV" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByRole("button", { name: "Аналитика" }));
    fetchMock.mockRestore(); createUrl.mockRestore(); revokeUrl.mockRestore(); linkClick.mockRestore(); delete window.Telegram;
  });

  it("shows an API analytics error and retries", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ message: "Сервис временно недоступен" }), { status: 500, headers: { "Content-Type": "application/json" } }));
    render(<AnalyticsModal opened onClose={vi.fn()} show={show} demo={false} onEdit={vi.fn()} onAnnouncement={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(await screen.findByText("Сервис временно недоступен")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    fetchMock.mockRestore(); delete window.Telegram;
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

  it("loads, copies, tests and publishes a live announcement", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const clipboard = { writeText: vi.fn(async () => undefined) };
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
    const promotion = { html: "<b>Супер</b>", text: "Супер — запись", registrationUrl: "https://t.me/test", hasPoster: false, hasPublished: false, channels: [] };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => new Response(JSON.stringify(String(input).includes("/promotion") && !String(input).includes("/test") ? promotion : { ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const onPublished = vi.fn();
    render(<AnnouncementModal opened onClose={vi.fn()} show={show} demo={false} onEdit={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} onPublished={onPublished} />, { wrapper });
    expect(await screen.findByText("Активные рекламные каналы пока не добавлены.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Скопировать текст и ссылку" }));
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalledWith("Супер — запись"));
    fireEvent.click(screen.getByRole("button", { name: "Отправить тест себе" }));
    fireEvent.click(screen.getByRole("button", { name: "Опубликовать в основном канале" }));
    await waitFor(() => expect(onPublished).toHaveBeenCalled());
    fetchMock.mockRestore(); delete window.Telegram;
  });
});
