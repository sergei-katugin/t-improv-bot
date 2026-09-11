import { afterEach, describe, expect, it, vi } from "vitest";
import { api, authenticatedBlob } from "./api";

function setInitData(value: string) {
  Object.defineProperty(window, "Telegram", { configurable: true, value: { WebApp: { initData: value } } });
}

describe("api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setInitData("");
    history.replaceState({}, "", "/");
  });

  it("rejects requests outside Telegram", async () => {
    setInitData("");
    await expect(api("/private")).rejects.toThrow("Telegram не передал данные авторизации");
  });

  it("adds authorization and returns json", async () => {
    setInitData("signed-data");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 7 }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api<{ id: number }>("/shows", { method: "POST", body: JSON.stringify({ title: "Шоу" }) })).resolves.toEqual({ id: 7 });
    expect(fetchMock).toHaveBeenCalledWith("/shows", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "tma signed-data", "Content-Type": "application/json" }) }));
  });

  it("lets the WebView set the multipart boundary for poster uploads", async () => {
    setInitData("signed-data");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ hasPoster: true }) });
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    form.append("poster", new File(["image"], "poster.jpg", { type: "image/jpeg" }));

    await api("/shows/1/poster", { method: "POST", body: form });

    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("tma signed-data");
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("turns API field errors into a useful message", async () => {
    setInitData("signed-data");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, headers: new Headers({ "X-Request-ID": "req-1" }), json: async () => ({ field: "title" }) }));
    await expect(api("/shows")).rejects.toThrow("Проверь поле: title · код req-1");
  });

  it("preserves the response status for access handling", async () => {
    setInitData("signed-data");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, headers: new Headers(), json: async () => ({ error: "organizer_access_required" }) }));

    await expect(api("/shows")).rejects.toMatchObject({ status: 403 });
  });

  it("downloads authenticated blobs and reports failures", async () => {
    setInitData("signed-data");
    const file = new Blob(["csv"]);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, blob: async () => file })
      .mockResolvedValueOnce({ ok: false, headers: new Headers({ "X-Request-ID": "blob-1" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(authenticatedBlob("/report.csv")).resolves.toBe(file);
    await expect(authenticatedBlob("/broken.csv")).rejects.toThrow("Не удалось загрузить файл · код blob-1");
  });
});
