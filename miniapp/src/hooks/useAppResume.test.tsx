import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAppResume } from "./useAppResume";

function ResumeProbe({ onResume }: { onResume: () => void }) {
  useAppResume(onResume);
  return null;
}

describe("useAppResume", () => {
  it("ignores a focus gained by the first click but handles a real page restore", () => {
    const onResume = vi.fn();
    render(<ResumeProbe onResume={onResume} />);

    act(() => window.dispatchEvent(new Event("focus")));
    expect(onResume).not.toHaveBeenCalled();

    act(() => window.dispatchEvent(new Event("pageshow")));
    expect(onResume).toHaveBeenCalledOnce();
  });
});
