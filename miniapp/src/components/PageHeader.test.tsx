import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { PageHeader } from "./PageHeader";

it("renders one page heading and an optional distinct subtitle", () => {
  const { rerender } = render(<PageHeader title="Очень длинное название шоу" subtitle="Экспериментаторы" />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading")).toHaveAttribute("title", "Очень длинное название шоу");
  expect(screen.getByText("Экспериментаторы")).toHaveClass("page-header-subtitle");
  rerender(<PageHeader title="Мои афиши" />);
  expect(screen.queryByText("Экспериментаторы")).not.toBeInTheDocument();
});
