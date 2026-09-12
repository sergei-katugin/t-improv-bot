import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RootNavigation } from "./BottomActionBar";

describe("RootNavigation", () => {
  it("separates administration from app settings", () => {
    const onAdministration = vi.fn();
    const onSettings = vi.fn();
    render(<RootNavigation onShows={() => undefined} onCreate={() => undefined} onAdministration={onAdministration} onSettings={onSettings} />);
    expect(screen.getAllByRole("button")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "Управление" }));
    fireEvent.click(screen.getByRole("button", { name: "Настройки" }));
    expect(onAdministration).toHaveBeenCalledOnce();
    expect(onSettings).toHaveBeenCalledOnce();
  });

  it("moves one shared selection between tabs without replacing it", () => {
    const actions = { onShows: vi.fn(), onCreate: vi.fn(), onAdministration: vi.fn(), onSettings: vi.fn() };
    const view = render(<RootNavigation active="shows" {...actions} />);
    const navigation = screen.getByRole("navigation");
    const selection = navigation.querySelector(".bottom-nav-selection");
    expect(navigation.style.getPropertyValue("--nav-count")).toBe("4");
    expect(navigation.style.getPropertyValue("--nav-index")).toBe("0");
    view.rerender(<RootNavigation active="settings" {...actions} />);
    expect(navigation.style.getPropertyValue("--nav-index")).toBe("3");
    expect(navigation.querySelector(".bottom-nav-selection")).toBe(selection);
    expect(screen.getByRole("button", { name: "Настройки" })).toHaveAttribute("aria-current", "page");
  });
});
