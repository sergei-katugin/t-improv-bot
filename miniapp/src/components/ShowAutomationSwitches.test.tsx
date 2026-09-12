import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ShowAutomationSwitches } from "./ShowAutomationSwitches";


it("explains feedback without an entry-tracking switch", () => {
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
  expect(switches).toHaveLength(1);
  expect(screen.queryByLabelText("Включить check-in")).not.toBeInTheDocument();
});
