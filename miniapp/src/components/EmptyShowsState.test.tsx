import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { expect, it, vi } from "vitest";

import { EmptyShowsState } from "./EmptyShowsState";


it("offers creation directly in the upcoming empty state", () => {
  const onCreate = vi.fn();
  render(<MantineProvider><EmptyShowsState status="upcoming" onCreate={onCreate} /></MantineProvider>);

  fireEvent.click(screen.getByRole("button", { name: "Создать афишу" }));

  expect(onCreate).toHaveBeenCalledOnce();
  expect(screen.getByText("Создай первую афишу — она появится в этом разделе.")).toBeInTheDocument();
});


it("does not offer creation in the past empty state", () => {
  render(<MantineProvider><EmptyShowsState status="past" onCreate={vi.fn()} /></MantineProvider>);

  expect(screen.queryByRole("button", { name: "Создать афишу" })).not.toBeInTheDocument();
});
