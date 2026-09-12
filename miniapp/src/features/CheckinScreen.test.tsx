import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CheckinScreen, CheckinHome } from "./CheckinScreen";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({ api: vi.fn() }));
const snapshot = { id: 1, title: "Шоу", mode: "counter", reportEvery: 10, arrived: 12, booked: 20, remaining: 8, percent: 60, items: [] };
const wrapper = ({ children }: { children: React.ReactNode }) => <MantineProvider>{children}</MantineProvider>;
describe("Check-in", () => {
  beforeEach(() => vi.mocked(api).mockReset());
  it("shows percentage and sends a guarded +2 count", async () => {
    vi.mocked(api).mockResolvedValue(snapshot);
    render(<CheckinScreen showId={1} />, { wrapper });
    expect(await screen.findByText("Пришли и ждут: 12")).toBeInTheDocument();
    expect(screen.getByText("Из 20 записанных · 60%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+2" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/miniapp/shows/1/checkin", expect.objectContaining({ body: JSON.stringify({ expected: 12, delta: 2 }) })));
    expect(screen.queryByRole("button", { name: /Пригласить/ })).not.toBeInTheDocument();
  });
  it("searches named entries and marks the whole party", async () => {
    const entry = { id: 5, kind: "registration", name: "Анна", booked: 3, arrived: 1 };
    vi.mocked(api).mockResolvedValue({ ...snapshot, mode: "named", items: [entry] });
    render(<CheckinScreen showId={1} />, { wrapper });
    expect(await screen.findByText("Анна")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Пришли все" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/miniapp/shows/1/checkin", expect.objectContaining({ method: "POST" })));
    fireEvent.change(screen.getByLabelText("Поиск зрителя"), { target: { value: "Анна" } });
    await waitFor(() => expect(api).toHaveBeenCalledWith("/api/miniapp/shows/1/checkin?search=%D0%90%D0%BD%D0%BD%D0%B0"));
  });
  it("routes the employee directly into their only show", async () => {
    vi.mocked(api).mockImplementation(async (path) => path?.endsWith("/checkin/shows") ? { items: [{ id: 1, title: "Шоу", date: "Сегодня" }] } : snapshot);
    render(<CheckinHome />, { wrapper });
    expect(await screen.findByText("Пришли и ждут: 12")).toBeInTheDocument();
  });
});
