import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ShowStepper } from "./ShowStepper";

function renderStepper(allowAllSteps = false) {
  const onStepChange = vi.fn();
  render(<MantineProvider><ShowStepper active={1} labels={["Основное", "Место", "Запись"]} allowAllSteps={allowAllSteps} onStepChange={onStepChange} /></MantineProvider>);
  return onStepChange;
}

describe("ShowStepper", () => {
  it("keeps future steps disabled while creating", () => {
    renderStepper();
    expect(screen.getByRole("button", { name: "Шаг 3: Запись" })).toBeDisabled();
  });

  it("allows direct navigation while editing", () => {
    const onStepChange = renderStepper(true);
    fireEvent.click(screen.getByRole("button", { name: "Шаг 3: Запись" }));
    expect(onStepChange).toHaveBeenCalledWith(2);
  });
});
