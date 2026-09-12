import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TelegramTabs } from "./TelegramTabs";

it("keeps the selected tab accessible and updates selection", () => {
  const onChange = vi.fn();
  const items = [{ value: "upcoming", label: "Будущие" }, { value: "past", label: "Прошедшие" }];
  const view = (value: string) => <MantineProvider><TelegramTabs
    value={value} onChange={onChange} items={items} label="Период афиш" />
  </MantineProvider>;
  const { rerender } = render(view("upcoming"));
  expect(screen.getByRole("tablist", { name: "Период афиш" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Будущие" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("tab", { name: "Прошедшие" }));
  expect(onChange).toHaveBeenCalledWith("past");
  rerender(view("past"));
  expect(screen.getByRole("tab", { name: "Прошедшие" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Будущие" })).toHaveAttribute("aria-selected", "false");
});

it("supports keyboard navigation without losing focus", () => {
  const onChange = vi.fn();
  render(<MantineProvider><TelegramTabs value="system" onChange={onChange} label="Тема"
    items={[{ value: "system", label: "Системная" }, { value: "light", label: "Светлая" }, { value: "dark", label: "Тёмная" }]} />
  </MantineProvider>);
  const first = screen.getByRole("tab", { name: "Системная" });
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Светлая" })).toHaveFocus();
  expect(onChange).toHaveBeenCalledWith("light");
});
