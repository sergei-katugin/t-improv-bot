import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AttendeeList } from "./AttendeeList";

describe("AttendeeList", () => {
  it("renders people as simple rows without status controls", () => {
    render(<MantineProvider><AttendeeList items={[{ id: 1, name: "Сергей", username: "sergey", guests: 2 }]} /></MantineProvider>);
    expect(screen.getByText("Сергей")).toBeInTheDocument();
    expect(screen.getByText("3 места")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText("Ожидает ответа")).not.toBeInTheDocument();
  });
});
