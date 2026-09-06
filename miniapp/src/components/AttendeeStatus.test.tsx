import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AttendeeStatus } from "./AttendeeStatus";

describe("AttendeeStatus", () => {
  it.each([
    [{ checkedInCount: 1 }, "Пришёл"],
    [{ checkedInCount: 0, confirmed: true }, "Подтвердил"],
    [{ checkedInCount: 0, confirmed: false }, "Не придёт"],
    [{ checkedInCount: 0, confirmed: null }, "Ожидает ответа"],
    [{ checkedInCount: 0, manual: true }, "Добавлен вручную"],
  ])("shows the semantic registration state", (props, label) => {
    render(<MantineProvider><AttendeeStatus {...props} /></MantineProvider>);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
