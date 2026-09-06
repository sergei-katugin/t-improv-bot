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
});
