import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Show } from "../types";
import { ShowCard } from "./ShowCard";

const show = { id: 1, title: "Супер", teamName: "Экспериментаторы", showDateLabel: "5 сентября, 20:00", location: "Театр", city: "Лимасол", occupiedSeats: 12, maxSeats: 80, isPast: false } as Show;

describe("ShowCard", () => {
  it("renders capacity and opens the show", () => {
    const onClick = vi.fn();
    render(<MantineProvider><ShowCard show={show} onClick={onClick} /></MantineProvider>);
    expect(screen.getByText("12 / 80")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("labels past capacity differently", () => {
    render(<MantineProvider><ShowCard show={{ ...show, isPast: true }} onClick={() => undefined} /></MantineProvider>);
    expect(screen.getByText("Было записано")).toBeInTheDocument();
  });

  it("marks a show without an announcement as a draft", () => {
    const { rerender } = render(<MantineProvider><ShowCard show={{ ...show, hasPublished: false }} onClick={() => undefined} /></MantineProvider>);
    expect(screen.getByText("Черновик")).toBeInTheDocument();
    rerender(<MantineProvider><ShowCard show={{ ...show, hasPublished: true }} onClick={() => undefined} /></MantineProvider>);
    expect(screen.queryByText("Черновик")).not.toBeInTheDocument();
  });
});
