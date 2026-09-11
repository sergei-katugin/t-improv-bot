import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { newShowForm } from "../features/ShowForm";
import { clearShowFormDraft, readShowFormDraft, showFormDraftKey, useShowFormDraft } from "./useShowFormDraft";

describe("show form draft", () => {
  afterEach(() => { localStorage.clear(); vi.useRealTimers(); });

  it("saves and restores a new-show draft", () => {
    vi.useFakeTimers();
    const value = { ...newShowForm(), title: "Черновик", titleNewcomer: "Понятный заголовок" };
    const key = showFormDraftKey();
    renderHook(() => useShowFormDraft(key, true, value, "3", 2));
    act(() => vi.advanceTimersByTime(300));

    expect(readShowFormDraft(key, newShowForm())).toMatchObject({ value, venueId: "3", activeStep: 2 });
  });

  it("isolates edited shows and ignores malformed drafts", () => {
    const first = showFormDraftKey(1);
    const second = showFormDraftKey(2);
    localStorage.setItem(first, "broken");
    localStorage.setItem(second, JSON.stringify({ version: 1, value: {}, venueId: null, activeStep: 9 }));

    expect(readShowFormDraft(first, newShowForm())).toBeNull();
    expect(readShowFormDraft(second, newShowForm())).toBeNull();
    clearShowFormDraft(first);
    expect(localStorage.getItem(first)).toBeNull();
  });
});
