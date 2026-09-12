import { renderHook, act } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useKeyboardViewport } from "./useKeyboardViewport";

afterEach(() => { vi.unstubAllGlobals(); document.body.replaceChildren(); });

it("ignores browser chrome, tracks the keyboard and cleans up", () => {
  const viewport = Object.assign(new EventTarget(), { height: window.innerHeight, offsetTop: 0, scale: 1 });
  vi.stubGlobal("visualViewport", viewport);
  const input = document.createElement("input");
  document.body.append(input);
  const { unmount } = renderHook(useKeyboardViewport);
  act(() => { input.focus(); viewport.height = window.innerHeight - 60; viewport.dispatchEvent(new Event("resize")); });
  expect(document.documentElement.dataset.keyboard).toBe("closed");
  act(() => { viewport.height = window.innerHeight - 300; viewport.dispatchEvent(new Event("resize")); });
  expect(document.documentElement.dataset.keyboard).toBe("open");
  expect(document.documentElement.style.getPropertyValue("--keyboard-inset")).toBe("300px");
  act(() => { viewport.height = window.innerHeight; viewport.dispatchEvent(new Event("resize")); });
  expect(document.documentElement.dataset.keyboard).toBe("closed");
  unmount();
  expect(document.documentElement.dataset.keyboard).toBeUndefined();
  expect(document.documentElement.style.getPropertyValue("--keyboard-inset")).toBe("");
});

it("does not mistake zooming or an unfocused page for a keyboard", () => {
  const viewport = Object.assign(new EventTarget(), { height: 100, offsetTop: 0, scale: 1 });
  vi.stubGlobal("visualViewport", viewport);
  renderHook(useKeyboardViewport);
  expect(document.documentElement.dataset.keyboard).toBe("closed");
  const input = document.createElement("input");
  document.body.append(input);
  act(() => { viewport.scale = 2; input.focus(); });
  expect(document.documentElement.dataset.keyboard).toBe("closed");
});
