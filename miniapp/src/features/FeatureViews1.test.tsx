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
import { showFormDraftKey } from "../hooks/useShowFormDraft";

const wrapper = ({ children }: { children: ReactNode }) => <MantineProvider>{children}</MantineProvider>;
const show = { id: 1, title: "Супер", teamName: "Экспериментаторы", showDateLabel: "5 сентября, 20:00", showDateLocal: "2027-09-05T20:00", location: "Театр", city: "Лимасол", occupiedSeats: 10, maxSeats: 80, isActive: true, isPast: false, registrarUsername: "sergey", posterText: "Описание", hasPublished: true } as Show;
const options: Options = {
  teams: [{ id: 1, name: "Экспериментаторы", members: "@sergey" }],
  venues: [{ id: 1, name: "Театр", city: "Лимасол", mapsUrl: "https://example.com", defaultSeats: 80 }],
  adChannels: [{ id: 1, username: "events", isActive: true }],
};
const me: Me = { id: 1, firstName: "Sergey", username: "sergey", role: "admin" };


describe("ShowForm", () => {
  it("opens as a closable animated bottom sheet", () => {
    const onClose = vi.fn();
    render(<ShowForm opened initial={null} options={options} me={me} reloadOptions={async () => undefined} onClose={onClose} onSaved={vi.fn()} />, { wrapper });
    const dialog = screen.getByRole("dialog", { name: "Новая афиша" });
    expect(dialog).toHaveClass("show-form-sheet");
    fireEvent.click(dialog.querySelector(".show-form-close")!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("restores an autosaved new-show draft", () => {
    const value = { ...newShowForm(), title: "Несохранённая афиша", titleNewcomer: "Название для первого знакомства" };
    localStorage.setItem(showFormDraftKey(), JSON.stringify({ version: 1, value, venueId: null, activeStep: 0 }));

    render(<ShowForm opened initial={null} options={options} me={me} reloadOptions={async () => undefined} onClose={vi.fn()} onSaved={vi.fn()} />, { wrapper });

    expect(screen.getByRole("textbox", { name: /^Название$/ })).toHaveValue("Несохранённая афиша");
    expect(screen.getByRole("textbox", { name: /Название для новичков/ })).toHaveValue("Название для первого знакомства");
    localStorage.removeItem(showFormDraftKey());
  });

  it("defaults registration closing to one hour before the show", () => {
    expect(newShowForm().maxGuests).toBe(6);
    expect(newShowForm().feedbackEnabled).toBe(true);
  });

  it("allows an editor to inspect every step", () => {
    render(<ShowForm opened initial={show} options={options} me={me} reloadOptions={async () => undefined} onClose={() => undefined} onSaved={() => undefined} />, { wrapper });
    expect(screen.getByRole("textbox", { name: /Название для новичков/ })).toHaveValue("");
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
    fireEvent.change(screen.getByLabelText("Профессиональное описание"), { target: { value: "Обновлённый текст" } });
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
    fireEvent.change(await screen.findByRole("textbox", { name: /^Название$/ }), { target: { value: "Премьера" } });
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

  it("opens teams in a closable sheet", async () => {
    render(<ManagementModal opened onClose={() => undefined} me={me} options={options} reload={async () => undefined} themePreference="system" onThemePreferenceChange={() => undefined} onResetLocalData={() => undefined} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Команды/ }));
    const dialog = await screen.findByRole("dialog", { name: "Команды" });
    expect(within(dialog).getByText("Экспериментаторы")).toBeInTheDocument();
    expect(dialog).not.toHaveAttribute("data-full-screen");
    expect(within(dialog).getByRole("button", { name: "Закрыть команды" })).toBeInTheDocument();
  });

  it("opens venue sheet and channel editor", async () => {
    const props = { opened: true, onClose: vi.fn(), me, options, reload: async () => undefined, themePreference: "system" as const, onThemePreferenceChange: vi.fn(), onResetLocalData: vi.fn(), backHandlerRef: createRef<(() => boolean) | null>() };
    const view = render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Площадки/ }));
    const venuesDialog = await screen.findByRole("dialog", { name: "Площадки" });
    expect(venuesDialog).not.toHaveAttribute("data-full-screen");
    expect(within(venuesDialog).getByRole("button", { name: "Закрыть площадки" })).toBeInTheDocument();
    fireEvent.click(within(venuesDialog).getByRole("button", { name: /Добавить площадку/ }));
    expect(await screen.findByRole("dialog", { name: "Новая площадка" })).toBeInTheDocument();
    view.unmount();

    render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Каналы для анонсов/ }));
    const channelsDialog = await screen.findByRole("dialog", { name: "Каналы для анонсов" });
    expect(channelsDialog).not.toHaveAttribute("data-full-screen");
    expect(within(channelsDialog).getByRole("button", { name: "Закрыть каналы" })).toBeInTheDocument();
    fireEvent.click(within(channelsDialog).getByRole("button", { name: /Добавить канал/ }));
    expect(await screen.findByRole("dialog", { name: "Новый рекламный канал" })).toBeInTheDocument();
  });

  it("shows access controls and the audit log", async () => {
    history.replaceState({}, "", "/?preview=1");
    render(<ManagementModal opened onClose={vi.fn()} me={me} options={options} reload={async () => undefined} themePreference="system" onThemePreferenceChange={vi.fn()} onResetLocalData={vi.fn()} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Доступ и журнал/ }));
    const accessDialog = await screen.findByRole("dialog", { name: "Доступ и журнал" });
    expect(within(accessDialog).getByText("@anna_impro")).toBeInTheDocument();
    expect(accessDialog).not.toHaveAttribute("data-full-screen");
    expect(within(accessDialog).getByRole("button", { name: "Закрыть доступ и журнал" })).toBeInTheDocument();
    fireEvent.click(within(accessDialog).getByRole("button", { name: "Журнал действий" }));
    const auditDialog = await screen.findByRole("dialog", { name: "Журнал действий" });
    expect(within(auditDialog).getByText("Афиша опубликована")).toBeInTheDocument();
    expect(auditDialog).not.toHaveAttribute("data-full-screen");
    expect(within(auditDialog).getByRole("button", { name: "Закрыть журнал действий" })).toBeInTheDocument();
    history.replaceState({}, "", "/");
  });

  it("creates a team in the teams sheet", async () => {
    history.replaceState({}, "", "/?preview=1");
    const reload = vi.fn(async () => undefined);
    render(<ManagementModal opened onClose={vi.fn()} me={me} options={options} reload={reload} themePreference="system" onThemePreferenceChange={vi.fn()} onResetLocalData={vi.fn()} backHandlerRef={createRef()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Команды/ }));
    const teamsDialog = await screen.findByRole("dialog", { name: "Команды" });
    fireEvent.click(within(teamsDialog).getByRole("button", { name: /Добавить команду/ }));
    const editorDialog = await screen.findByRole("dialog", { name: "Новая команда" });
    fireEvent.change(within(editorDialog).getByLabelText("Название"), { target: { value: "Новая команда" } });
    fireEvent.change(within(editorDialog).getByLabelText("Telegram-ники участников"), { target: { value: "@valid_user" } });
    fireEvent.click(within(editorDialog).getByRole("button", { name: "Добавить команду" }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    history.replaceState({}, "", "/");
  });

  it("edits existing team and venue records", async () => {
    history.replaceState({}, "", "/?preview=1");
    const reload = vi.fn(async () => undefined);
    const props = { opened: true, onClose: vi.fn(), me, options, reload, themePreference: "system" as const, onThemePreferenceChange: vi.fn(), onResetLocalData: vi.fn(), backHandlerRef: createRef<(() => boolean) | null>() };
    const teamView = render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Команды/ }));
    const teamsDialog = await screen.findByRole("dialog", { name: "Команды" });
    fireEvent.click(within(teamsDialog).getByRole("button", { name: "Изменить" }));
    const editorDialog = await screen.findByRole("dialog", { name: "Редактировать команду" });
    fireEvent.change(within(editorDialog).getByRole("textbox", { name: /Название/ }), { target: { value: "Экспериментаторы 2" } });
    fireEvent.click(within(editorDialog).getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    teamView.unmount();

    render(<ManagementModal {...props} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Площадки/ }));
    const venuesDialog = await screen.findByRole("dialog", { name: "Площадки" });
    fireEvent.click(within(venuesDialog).getByRole("button", { name: "Изменить" }));
    const venueEditorDialog = await screen.findByRole("dialog", { name: "Редактировать площадку" });
    fireEvent.change(within(venueEditorDialog).getByRole("textbox", { name: /Название/ }), { target: { value: "Театр 2" } });
    fireEvent.change(within(venueEditorDialog).getByRole("textbox", { name: "Ссылка на карту" }), { target: { value: "https://maps.example/new" } });
    fireEvent.click(within(venueEditorDialog).getByRole("button", { name: "Сохранить" }));
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
