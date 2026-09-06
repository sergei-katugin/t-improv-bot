import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoot } from "./App";

describe("AppRoot preview flow", () => {
  afterEach(() => vi.unstubAllGlobals());

  beforeEach(() => {
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
});
