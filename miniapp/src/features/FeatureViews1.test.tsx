import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createRef, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Me, Options, Show } from "../types";
import { AnnouncementModal } from "./AnnouncementModal";
import { AttendeesModal } from "./AttendeesModal";
import { AnalyticsModal } from "../components/AnalyticsModal";
import { ManagementModal } from "./ManagementModal";
import { newShowForm, ShowForm } from "./ShowForm";
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
    expect(newShowForm().maxGuests).toBe(6);
    expect(newShowForm().feedbackEnabled).toBe(true);
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

  it("saves an unpublished draft without asking about viewer notifications", async () => {
    history.replaceState({}, "", "/?preview=1");
    const onSaved = vi.fn();
    render(<ShowForm opened initial={{ ...show, hasPublished: false }} options={options} me={me} reloadOptions={async () => undefined} onClose={vi.fn()} onSaved={onSaved} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Шаг 4: Афиша" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить изменения" }));

    expect(screen.queryByRole("dialog", { name: "Уведомить зрителей?" })).not.toBeInTheDocument();
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
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
