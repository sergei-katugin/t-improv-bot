import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Show } from "../types";
import { ShowNavigation } from "./ShowNavigation";
import { CheckinNavigation } from "../features/CheckinNavigation";

const show = { id: 1, title: "Супер", isPast: false, hasPublished: false } as Show;
const handlers = () => ({ onShow: vi.fn(), onEdit: vi.fn(), onAnnouncement: vi.fn(), onAnalytics: vi.fn(), onRegistration: vi.fn(), onMore: vi.fn() });

describe("ShowNavigation", () => {
  it("opens check-in on the show day even after the scheduled start", () => {
    const open = vi.fn();
    render(<CheckinNavigation.Provider value={open}><ShowNavigation show={{ ...show, isPast: true, isShowDay: true, isActive: true, checkinEnabled: true }} {...handlers()} /></CheckinNavigation.Provider>);
    fireEvent.click(screen.getByRole("button", { name: "Вход" }));
    expect(open).toHaveBeenCalledWith(1);
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument();
  });

  it.each([{ isShowDay: false }, { isActive: false }, { checkinEnabled: false }])("hides entry outside an active check-in day: %s", (override) => {
    render(<ShowNavigation show={{ ...show, isShowDay: true, isActive: true, checkinEnabled: true, ...override }} {...handlers()} />);
    expect(screen.queryByRole("button", { name: "Вход" })).not.toBeInTheDocument();
  });
  it("always shows announcement instead of a registration link", () => {
    const actions = handlers();
    render(<ShowNavigation show={show} {...actions} />);
    expect(screen.getByRole("button", { name: "Анонс" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ссылка" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Аналитика" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Действия" }));
    expect(actions.onMore).toHaveBeenCalledOnce();
  });

  it("replaces obsolete actions for a past show", () => {
    render(<ShowNavigation show={{ ...show, isPast: true }} {...handlers()} />);
    expect(screen.getByRole("button", { name: "Аналитика" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Настройки" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Действия" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Анонс" })).toBeInTheDocument();
  });
});
