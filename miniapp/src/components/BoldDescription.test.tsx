import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BOLD_FRAGMENT_PATTERN, BoldDescription } from "./BoldDescription";

describe("BoldDescription", () => {
  it("renders bold fragments across line breaks without a dotAll regexp", () => {
    const { container } = render(<BoldDescription text={"Начало **важная\nфраза** конец"} />);

    expect(screen.getByText(/важная/).tagName).toBe("STRONG");
    expect(container).toHaveTextContent("Начало важная фраза конец");
  });

  it("keeps the expression compatible with Telegram Desktop webviews", () => {
    expect(BOLD_FRAGMENT_PATTERN.flags).toBe("g");
    expect(BOLD_FRAGMENT_PATTERN.flags).not.toContain("s");
  });
});
