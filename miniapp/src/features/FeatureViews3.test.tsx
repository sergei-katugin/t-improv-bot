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


describe("AttendeesModal", () => {
  it("shows viewers immediately as a simple list", () => {
    render(<AttendeesModal opened onClose={vi.fn()} show={show} demo backHandlerRef={createRef<(() => boolean) | null>()} onEdit={vi.fn()} onAnnouncement={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(screen.getByText("Анна Смирнова")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Фильтр зрителей"), { target: { value: "Анна" } });
    expect(screen.queryByRole("button", { name: "Отменить" })).not.toBeInTheDocument();
  });

  it("opens the manual attendee form", async () => {
    render(<AttendeesModal opened onClose={vi.fn()} show={show} demo backHandlerRef={createRef<(() => boolean) | null>()} onEdit={vi.fn()} onAnnouncement={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "➕ Добавить человека" }));
    const dialog = await screen.findByRole("dialog", { name: "Добавить человека" });
    expect(within(dialog).getByRole("textbox", { name: "Полное имя" })).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "Контакт" })).toHaveAttribute("placeholder", "@username");
    expect(within(dialog).getByRole("button", { name: "Добавить" })).toBeDisabled();
  });

  it("loads and appends viewers from the API", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const second = String(input).includes("cursor=next");
      const payload = { occupied: second ? 2 : 1, maxSeats: 20, arrived: 0, hasMore: !second, nextOffset: 100, nextCursor: second ? null : "next",
        registrations: [{ id: second ? 2 : 1, name: second ? "Борис" : "Анна", guests: 0, confirmed: null, checkedInCount: 0, source: "telegram" }], manual: [],
        waitlist: second ? [] : [{ id: 3, name: "В листе ожидания", username: "waiting", position: 1 }] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(<AttendeesModal opened onClose={vi.fn()} show={show} demo={false} backHandlerRef={createRef()} onEdit={vi.fn()} onAnnouncement={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} />, { wrapper });
    expect(await screen.findByText("Анна")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText("Борис")).toBeInTheDocument();
    expect(screen.getByText("Анна")).toBeInTheDocument();
    expect(screen.getByText("В листе ожидания")).toBeInTheDocument();
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
    const confirmation = await screen.findByRole("dialog", { name: "Повторить публикацию?" });
    expect(within(confirmation).getByRole("combobox", { name: "Аудитория повторной публикации" })).toHaveValue("Знакомы с импровом");
    fireEvent.click(await screen.findByRole("button", { name: "Да, отправить повторно" }));
    await waitFor(() => expect(screen.queryByText("Повторить публикацию?")).not.toBeInTheDocument());
  });

  it("sends a test announcement in preview mode", async () => {
    render(<AnnouncementModal opened onClose={vi.fn()} show={show} demo onEdit={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} onPublished={vi.fn()} />, { wrapper });
    expect(screen.getByRole("combobox", { name: "Для кого этот анонс" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Отправить тест себе" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Отправить тест себе" })).not.toBeDisabled());
  });

  it("loads, copies, tests and publishes a live announcement", async () => {
    window.Telegram = { WebApp: { initData: "signed", initDataUnsafe: {}, colorScheme: "dark", onEvent: vi.fn(), offEvent: vi.fn() } } as unknown as typeof window.Telegram;
    const clipboard = { writeText: vi.fn(async () => undefined) };
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
    const promotion = { html: "<b>Супер</b>", text: "Супер — запись", registrationUrl: "https://t.me/test", hasPoster: true, hasPublished: false, channels: [] };
    const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:announcement-poster");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).endsWith("/poster")
      ? new Response(new Blob(["image"], { type: "image/jpeg" }), { status: 200 })
      : new Response(JSON.stringify(String(input).includes("/promotion") && !String(input).includes("/test") ? promotion : { ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const onPublished = vi.fn();
    render(<AnnouncementModal opened onClose={vi.fn()} show={show} demo={false} onEdit={vi.fn()} onAnalytics={vi.fn()} onRegistration={vi.fn()} onMore={vi.fn()} onPublished={onPublished} />, { wrapper });
    expect(await screen.findByText("Активные рекламные каналы пока не добавлены.")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Изображение афиши в предпросмотре" })).toHaveAttribute("src", "blob:announcement-poster");
    expect(createUrl).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Скопировать текст и ссылку" }));
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalledWith("Супер — запись"));
    fireEvent.click(screen.getByRole("button", { name: "Отправить тест себе" }));
    fireEvent.click(screen.getByRole("button", { name: "Опубликовать в основном канале" }));
    await waitFor(() => expect(onPublished).toHaveBeenCalled());
    fetchMock.mockRestore(); delete window.Telegram;
  });
});
