import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AttentionCenter } from "./AttentionCenter";

describe("AttentionCenter", () => {
  it("opens a selected warning", () => {
    const onOpen = vi.fn();
    const item = { showId: 1, showTitle: "Супер", kind: "announcement" as const, label: "Опубликовать анонс" };
    render(<MantineProvider><AttentionCenter items={[item]} onOpen={onOpen} /></MantineProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Опубликовать анонс/ }));
    expect(onOpen).toHaveBeenCalledWith(item);
  });
});
