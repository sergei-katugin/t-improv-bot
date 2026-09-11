import { MantineProvider } from "@mantine/core";
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Show } from "../types";
import { AppearanceSettings } from "./AppearanceSettings";
import { MiniAppOnboarding } from "./MiniAppOnboarding";
import { ShowDetails } from "./ShowDetails";
import { ShowsHeader } from "./ShowsHeader";

const wrapper = ({ children }: { children: ReactNode }) => <MantineProvider>{children}</MantineProvider>;
const show = { id: 1, title: "Супер", teamName: "Экспериментаторы", showDateLabel: "5 сентября, 20:00", location: "Театр", locationUrl: "https://example.com", city: "Лимасол", occupiedSeats: 20, maxSeats: 80, isActive: true, isPast: false, registrarUsername: "sergey", posterText: "Описание" } as Show;

describe("ShowsHeader", () => {
  it("changes the period and opens filters", () => {
    const onStatusChange = vi.fn();
    const onToggleFilters = vi.fn();
    render(<ShowsHeader status="upcoming" onStatusChange={onStatusChange} filtersOpened={false} activeFilters={2} onToggleFilters={onToggleFilters} />, { wrapper });
    fireEvent.click(screen.getByRole("tab", { name: "Прошедшие" }));
    fireEvent.click(screen.getByRole("button", { name: "Фильтры: выбрано 2" }));
    expect(onStatusChange).toHaveBeenCalledWith("past");
    expect(onToggleFilters).toHaveBeenCalledOnce();
  });
});

describe("ShowDetails", () => {
  it("opens attendees and description", () => {
    const onAttendees = vi.fn();
    const onToggleDescription = vi.fn();
    render(<ShowDetails show={show} descriptionOpened={false} onToggleDescription={onToggleDescription} onAttendees={onAttendees} onEdit={() => undefined} onAnnouncement={() => undefined} onAnalytics={() => undefined} onRegistration={() => undefined} onMore={() => undefined} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /Открыть список зрителей/ }));
    fireEvent.click(screen.getByRole("button", { name: "Показать описание" }));
    expect(onAttendees).toHaveBeenCalledOnce();
    expect(onToggleDescription).toHaveBeenCalledOnce();
    expect(screen.getByText("Запись открыта")).toBeInTheDocument();
    expect(screen.getByText("Экспериментаторы")).toBeInTheDocument();
    expect(screen.getByText("Лимасол")).toBeInTheDocument();
  });

  it("shows a completed state without obsolete navigation", () => {
    render(<ShowDetails show={{ ...show, isPast: true }} descriptionOpened={false} onToggleDescription={() => undefined} onAttendees={() => undefined} onEdit={() => undefined} onAnnouncement={() => undefined} onAnalytics={() => undefined} onRegistration={() => undefined} onMore={() => undefined} />, { wrapper });
    expect(screen.getByText("Прошедшее")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument();
  });

  it("routes every available action and renders a cancelled draft", () => {
    const actions = {
      onAttendees: vi.fn(), onEdit: vi.fn(), onAnnouncement: vi.fn(),
      onAnalytics: vi.fn(), onRegistration: vi.fn(), onMore: vi.fn(),
    };
    render(<ShowDetails
      show={{ ...show, isActive: false, hasPublished: false, locationUrl: null, registrarUsername: null, posterText: null }}
      descriptionOpened={false}
      onToggleDescription={vi.fn()}
      {...actions}
    />, { wrapper });
    expect(screen.getByText("Отменено")).toBeInTheDocument();
    expect(screen.getByText("Черновик")).toBeInTheDocument();
    expect(screen.getByText("Эта афиша отменена. Новые записи недоступны.")).toBeInTheDocument();
    expect(screen.getByText("Театр").tagName).toBe("P");
    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    fireEvent.click(screen.getByRole("button", { name: "Анонс" }));
    fireEvent.click(screen.getByRole("button", { name: "Действия" }));
    expect(actions.onEdit).toHaveBeenCalledOnce();
    expect(actions.onAnnouncement).toHaveBeenCalledOnce();
    expect(actions.onMore).toHaveBeenCalledOnce();
  });
});

describe("MiniAppOnboarding", () => {
  it("walks through all slides and finishes", () => {
    const onFinish = vi.fn();
    render(<MiniAppOnboarding opened onFinish={onFinish} />, { wrapper });
    expect(screen.getByText("Создавай афиши и управляй шоу")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Дальше" }));
    fireEvent.click(screen.getByRole("button", { name: "Дальше" }));
    fireEvent.click(screen.getByRole("button", { name: "Дальше" }));
    fireEvent.click(screen.getByRole("button", { name: "Начать" }));
    expect(onFinish).toHaveBeenCalledOnce();
  });

  it("supports direct slide navigation and skip", () => {
    const onFinish = vi.fn();
    render(<MiniAppOnboarding opened onFinish={onFinish} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Перейти к шагу 3" }));
    expect(screen.getByText("Рабочий чат без лишних действий")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Пропустить" }));
    expect(onFinish).toHaveBeenCalledOnce();
  });

  it("supports horizontal swipes and ignores vertical gestures", () => {
    render(<MiniAppOnboarding opened onFinish={vi.fn()} />, { wrapper });
    const screenRoot = screen.getByText("Создавай афиши и управляй шоу").closest(".onboarding-screen")!;
    fireEvent.pointerDown(screenRoot, { pointerId: 1, isPrimary: true, clientX: 240, clientY: 100 });
    fireEvent.pointerUp(screenRoot, { pointerId: 1, clientX: 80, clientY: 110 });
    expect(screen.getByText("Новая афиша за четыре шага")).toBeInTheDocument();
    fireEvent.pointerDown(screenRoot, { pointerId: 2, isPrimary: true, clientX: 100, clientY: 80 });
    fireEvent.pointerUp(screenRoot, { pointerId: 2, clientX: 110, clientY: 200 });
    expect(screen.getByText("Новая афиша за четыре шага")).toBeInTheDocument();
    fireEvent.pointerDown(screenRoot, { pointerId: 3, isPrimary: true, clientX: 80, clientY: 100 });
    fireEvent.pointerUp(screenRoot, { pointerId: 3, clientX: 240, clientY: 110 });
    expect(screen.getByText("Создавай афиши и управляй шоу")).toBeInTheDocument();
  });

  it("cancels an interrupted swipe and ignores gestures starting on controls", () => {
    render(<MiniAppOnboarding opened onFinish={vi.fn()} />, { wrapper });
    const screenRoot = screen.getByText("Создавай афиши и управляй шоу").closest(".onboarding-screen")!;
    fireEvent.pointerDown(screenRoot, { pointerId: 1, isPrimary: true, clientX: 240, clientY: 100 });
    fireEvent.pointerCancel(screenRoot, { pointerId: 1 });
    fireEvent.pointerUp(screenRoot, { pointerId: 1, clientX: 20, clientY: 100 });
    expect(screen.getByText("Создавай афиши и управляй шоу")).toBeInTheDocument();

    const skip = screen.getByRole("button", { name: "Пропустить" });
    fireEvent.pointerDown(skip, { pointerId: 2, isPrimary: true, clientX: 240, clientY: 100 });
    fireEvent.pointerUp(screenRoot, { pointerId: 2, clientX: 20, clientY: 100 });
    expect(screen.getByText("Создавай афиши и управляй шоу")).toBeInTheDocument();
  });
});

describe("AppearanceSettings", () => {
  it("changes theme and confirms local reset", async () => {
    const onChange = vi.fn();
    const onReset = vi.fn();
    render(<AppearanceSettings value="system" onChange={onChange} onReset={onReset} />, { wrapper });
    fireEvent.click(screen.getByText("Тёмная"));
    expect(onChange).toHaveBeenCalledWith("dark");
    fireEvent.click(screen.getByRole("button", { name: "Сбросить локальные данные" }));
    fireEvent.click(await screen.findByRole("button", { name: "Сбросить" }));
    expect(onReset).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Сбросить локальные данные" }));
    fireEvent.click(await screen.findByRole("button", { name: "Отмена" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Сбросить Mini App?" })).not.toBeInTheDocument());
  });
});
