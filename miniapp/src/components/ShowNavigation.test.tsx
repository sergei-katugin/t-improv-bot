import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Show } from "../types";
import { ShowNavigation } from "./ShowNavigation";

const show = { id: 1, title: "Супер", isPast: false, hasPublished: false } as Show;
const handlers = () => ({ onShow: vi.fn(), onEdit: vi.fn(), onAnnouncement: vi.fn(), onAnalytics: vi.fn(), onRegistration: vi.fn(), onMore: vi.fn() });

describe("ShowNavigation", () => {
  it("shows announcement before publication and dispatches actions", () => {
    const actions = handlers();
    render(<ShowNavigation show={show} {...actions} />);
    expect(screen.getByRole("button", { name: "Анонс" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Аналитика" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ещё" }));
    expect(actions.onMore).toHaveBeenCalledOnce();
  });

  it("replaces obsolete actions for a past show", () => {
    render(<ShowNavigation show={{ ...show, isPast: true }} {...handlers()} />);
    expect(screen.getByRole("button", { name: "Аналитика" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Анонс" })).not.toBeInTheDocument();
  });
});
