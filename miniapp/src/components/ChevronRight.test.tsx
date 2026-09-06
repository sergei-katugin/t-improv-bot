import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChevronRight } from "./ChevronRight";

describe("ChevronRight", () => {
  it("is decorative and accepts a reusable class", () => {
    const { container } = render(<ChevronRight className="custom" />);
    const icon = container.querySelector("svg");
    expect(icon).toHaveClass("ios-chevron", "custom");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });
});
