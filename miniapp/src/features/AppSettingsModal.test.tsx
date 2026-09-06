import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppSettingsModal } from "./AppSettingsModal";

describe("AppSettingsModal", () => {
  it("keeps root navigation with settings active", () => {
    const onCreate = vi.fn();
    const onAdministration = vi.fn();
    render(<MantineProvider><AppSettingsModal opened onClose={vi.fn()} onCreate={onCreate} onAdministration={onAdministration} value="system" onChange={vi.fn()} onReset={vi.fn()} /></MantineProvider>);
    expect(screen.getByRole("button", { name: "Настройки" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));
    fireEvent.click(screen.getByRole("button", { name: "Управление" }));
    expect(onCreate).toHaveBeenCalledOnce();
    expect(onAdministration).toHaveBeenCalledOnce();
  });
});
