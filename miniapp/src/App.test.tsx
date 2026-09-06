import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { AppRoot } from "./App";

describe("AppRoot preview flow", () => {
  beforeEach(() => {
    history.replaceState({}, "", "/?preview=1");
    localStorage.setItem("miniapp-onboarding-v1", "done");
  });

  it("navigates through the main organizer surfaces", async () => {
    render(<AppRoot />);
    expect(screen.getByText("Истории на ночь")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Истории на ночь").closest("button")!);
    expect(screen.getByText("Открыть список зрителей")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Открыть список зрителей/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Список зрителей/ }));
    expect(await screen.findByText("Записались через бот")).toBeInTheDocument();
    const announcementButtons = screen.getAllByRole("button", { name: "Анонс" });
    fireEvent.click(announcementButtons[announcementButtons.length - 1]);
    expect(await screen.findByText("Публикация")).toBeInTheDocument();

    const moreButtons = screen.getAllByRole("button", { name: "Ещё" });
    fireEvent.click(moreButtons[moreButtons.length - 1]);
    expect(await screen.findByText("Создать копию")).toBeInTheDocument();

    const showButtons = screen.getAllByRole("button", { name: "Шоу" });
    fireEvent.click(showButtons[showButtons.length - 1]);
    fireEvent.click(screen.getByRole("button", { name: "← Все афиши" }));
    fireEvent.click(screen.getByRole("button", { name: "Настройки" }));
    expect(await screen.findByText("Тема оформления")).toBeInTheDocument();
  });
});
