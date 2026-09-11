import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoot } from "./App";

describe("AppRoot preview flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.Telegram;
  });

  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    history.replaceState({}, "", "/?preview=1");
    localStorage.setItem("miniapp-onboarding-v1", "done");
  });

  it("navigates through the main organizer surfaces", async () => {
    render(<AppRoot />);
    expect(screen.getByText("Истории на ночь")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Истории на ночь").closest("button")!);
    expect(screen.getByText("Открыть список зрителей")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Открыть список зрителей/ }));
    expect(await screen.findByText("Записались через бот")).toBeInTheDocument();
    const analyticsButtons = screen.getAllByRole("button", { name: "Аналитика" });
    fireEvent.click(analyticsButtons[analyticsButtons.length - 1]);
    expect(await screen.findByText("Источники записей")).toBeInTheDocument();

    const moreButtons = screen.getAllByRole("button", { name: "Действия" });
    fireEvent.click(moreButtons[moreButtons.length - 1]);
    expect(await screen.findByText("Создать копию")).toBeInTheDocument();

    const showButtons = screen.getAllByRole("button", { name: "Шоу" });
    fireEvent.click(showButtons[showButtons.length - 1]);
    fireEvent.click(screen.getByRole("button", { name: "← Все афиши" }));
    fireEvent.click(screen.getByRole("button", { name: "Настройки" }));
    expect(await screen.findByText("Тема оформления")).toBeInTheDocument();
  });

  it("opens creation, administration, settings and list filters", async () => {
    const clipboard = { writeText: vi.fn(async () => undefined) };
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
    render(<AppRoot />);
    fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
    expect(screen.getByLabelText("Фильтр по команде")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Скопировать ссылку" })[0]);
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Создать" }));
    expect(await screen.findByRole("dialog", { name: "Новая афиша" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("dialog", { name: "Новая афиша" }).querySelector(".mantine-Modal-close")!);
    fireEvent.click(screen.getByRole("button", { name: "Управление" }));
    expect(await screen.findByText("Администрирование")).toBeInTheDocument();
    const managementDialog = screen.getAllByRole("dialog").find((dialog) => dialog.textContent?.includes("Администрирование"))!;
    fireEvent.click(within(managementDialog).getByRole("button", { name: "Настройки" }));
    expect(await screen.findByRole("dialog", { name: "Настройки" })).toBeInTheDocument();
  });

  it("opens a draft announcement from the card quick action", async () => {
    render(<AppRoot />);
    fireEvent.click(screen.getAllByRole("button", { name: "Анонс" })[0]);
    expect(await screen.findByRole("dialog", { name: "Предпросмотр анонса" })).toBeInTheDocument();
    expect(document.title).toBe("Анонс");
  });

  it("shows a dedicated screen to Telegram users without organizer access", async () => {
    history.replaceState({}, "", "/");
    localStorage.removeItem("miniapp-onboarding-v1");
    const noop = () => undefined;
    const button = { show: noop, hide: noop, onClick: noop, offClick: noop };
    Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: {
      initData: "viewer-data", colorScheme: "dark", BackButton: button, SettingsButton: button,
      ready: noop, expand: noop, close: noop, onEvent: noop, offEvent: noop,
      setHeaderColor: noop, setBackgroundColor: noop, setBottomBarColor: noop,
    } } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers(),
      json: async () => ({ error: "organizer_access_required" }),
    }));

    render(<AppRoot />);

    expect(await screen.findByRole("heading", { name: "Административная Mini App" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "@sergey_katugin" })).toHaveAttribute("href", "https://t.me/sergey_katugin");
    await waitFor(() => expect(screen.queryByText("Создавай афиши и управляй шоу")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Создать" })).not.toBeInTheDocument();
  });

  it("finishes onboarding and can reset all local Mini App data", async () => {
    localStorage.removeItem("miniapp-onboarding-v1");
    sessionStorage.setItem("temporary", "value");
    render(<AppRoot />);
    fireEvent.click(await screen.findByRole("button", { name: "Пропустить" }));
    await waitFor(() => expect(localStorage.getItem("miniapp-onboarding-v1")).toBe("done"));
    fireEvent.click(screen.getByRole("button", { name: "Настройки" }));
    fireEvent.click(await screen.findByRole("button", { name: "Сбросить локальные данные" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Сбросить Mini App?" })).getByRole("button", { name: "Сбросить" }));
    expect(sessionStorage.getItem("temporary")).toBeNull();
    expect(await screen.findByText("Создавай афиши и управляй шоу")).toBeInTheDocument();
  });

  it("replaces old cards with skeletons while switching tabs", async () => {
    history.replaceState({}, "", "/");
    const noop = () => undefined;
    const button = { show: noop, hide: noop, onClick: noop, offClick: noop };
    Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: {
      initData: "test", colorScheme: "dark", BackButton: button, SettingsButton: button,
      ready: noop, expand: noop, close: noop, onEvent: noop, offEvent: noop,
      setHeaderColor: noop, setBackgroundColor: noop, setBottomBarColor: noop,
    } } });
    let resolvePast!: (response: Response) => void;
    const pastResponse = new Promise<Response>((resolve) => { resolvePast = resolve; });
    const response = (payload: unknown) => ({ ok: true, json: async () => payload, headers: new Headers() }) as Response;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/options")) return Promise.resolve(response({ teams: [], venues: [], adChannels: [] }));
      if (path.includes("/me")) return Promise.resolve(response({ id: 1, firstName: "Test", role: "admin" }));
      if (path.includes("status=past")) return pastResponse;
      return Promise.resolve(response({ items: [{ id: 1, title: "Будущее шоу", teamName: "Команда", showDateLabel: "Завтра", location: "Зал", city: "Город", isActive: true, maxSeats: 10, occupiedSeats: 2 }], hasMore: false, nextOffset: 1 }));
    }));

    render(<AppRoot />);
    expect(await screen.findByText("Будущее шоу")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Прошедшие" }));
    expect(screen.queryByText("Будущее шоу")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Загружаем афиши")).toBeInTheDocument();

    resolvePast(response({ items: [{ id: 2, title: "Прошедшее шоу", teamName: "Команда", showDateLabel: "Вчера", location: "Зал", city: "Город", isActive: false, isPast: true, maxSeats: 10, occupiedSeats: 8 }], hasMore: false, nextOffset: 1 }));
    expect(await screen.findByText("Прошедшее шоу")).toBeInTheDocument();
  });

  it("appends another page and reports a failed show refresh", async () => {
    history.replaceState({}, "", "/");
    const noop = () => undefined;
    const button = { show: noop, hide: noop, onClick: noop, offClick: noop };
    Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: {
      initData: "test", colorScheme: "dark", BackButton: button, SettingsButton: button,
      ready: noop, expand: noop, close: noop, onEvent: noop, offEvent: noop,
      setHeaderColor: noop, setBackgroundColor: noop, setBottomBarColor: noop,
    } } });
    const response = (payload: unknown, ok = true) => ({ ok, status: ok ? 200 : 500, json: async () => payload, headers: new Headers() }) as Response;
    let showRequests = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/options")) return response({ teams: [], venues: [], adChannels: [] });
      if (path.includes("/me")) return response({ id: 1, firstName: "Test", role: "admin" });
      if (path.includes("/attention")) return response({ items: [] });
      if (/\/shows\/1$/.test(path)) return response({}, false);
      if (path.includes("cursor=next")) return response({ items: [{ id: 2, title: "Вторая афиша", teamName: "Команда", showDateLabel: "Позже", location: "Зал", city: "Город", isActive: true, maxSeats: 10, occupiedSeats: 4 }], hasMore: false, nextCursor: null });
      showRequests += 1;
      return response({ items: [{ id: 1, title: "Первая афиша", teamName: "Команда", showDateLabel: "Скоро", location: "Зал", city: "Город", isActive: true, maxSeats: 10, occupiedSeats: 2 }], hasMore: true, nextCursor: "next" });
    }));

    render(<AppRoot />);
    expect(await screen.findByText("Первая афиша")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText("Вторая афиша")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Первая афиша").closest("button")!);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith("/api/miniapp/shows/1", expect.anything()));
    expect(screen.getByRole("heading", { name: "Первая афиша" })).toBeInTheDocument();
    expect(showRequests).toBeGreaterThan(0);
  });
});
