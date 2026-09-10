import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ShowAutomationSwitches } from "./ShowAutomationSwitches";


it("shows feedback first and explains both switches", () => {
  render(<MantineProvider><ShowAutomationSwitches
    feedbackEnabled
    checkinEnabled={false}
    onFeedbackChange={vi.fn()}
    onCheckinChange={vi.fn()}
  /></MantineProvider>);

  const switches = screen.getAllByRole("switch");
  expect(switches[0]).toHaveAccessibleName("Запрашивать отзывы после шоу");
  expect(switches[0]).toBeChecked();
  const feedbackInfo = screen.getByRole("button", { name: /Что означает «Запрашивать отзывы/ });
  fireEvent.click(feedbackInfo);
  expect(feedbackInfo).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("button", { name: /Что означает «Включить check-in/ })).toBeInTheDocument();
});
