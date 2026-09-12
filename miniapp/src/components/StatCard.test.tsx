import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { StatCard } from "./StatCard";

it("renders a labelled metric and supports unavailable values", () => {
  const { rerender } = render(<MantineProvider><StatCard label="Пришли" value="25 / 80" /></MantineProvider>);
  expect(screen.getByText("Пришли")).toBeInTheDocument();
  expect(screen.getByText("25 / 80")).toHaveClass("stat-card-value");
  rerender(<MantineProvider><StatCard label="Пришли" value="—" /></MantineProvider>);
  expect(screen.getByText("—")).toBeInTheDocument();
});
