import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { expect, it, vi } from "vitest";

import { AppDateTimePicker } from "./AppDateTimePicker";


it("uses the localized app calendar instead of a native datetime input", () => {
  render(<MantineProvider><AppDateTimePicker
    label="Дата и время"
    value="2027-09-05T20:00"
    onChange={vi.fn()}
  /></MantineProvider>);

  const input = screen.getByLabelText("Дата и время");
  expect(input).toHaveAttribute("type", "button");
  expect(input).toHaveTextContent("5 сентября 2027, 20:00");
  fireEvent.click(input);
  expect(input).toHaveAttribute("aria-expanded", "true");
  expect(input).toHaveAttribute("aria-haspopup", "dialog");
});
