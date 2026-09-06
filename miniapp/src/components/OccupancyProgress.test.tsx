import { describe, expect, it } from "vitest";
import { occupancyColor, occupancyPercentage } from "./OccupancyProgress";

describe("occupancyColor", () => {
  it.each([
    [0, "red"], [24.99, "red"],
    [25, "orange"], [49.99, "orange"],
    [50, "blue"], [74.99, "blue"],
    [75, "green"], [100, "green"],
  ] as const)("maps %s%% to %s", (percentage, color) => {
    expect(occupancyColor(percentage)).toBe(color);
  });
});

describe("occupancyPercentage", () => {
  it("clamps invalid and overfilled capacities", () => {
    expect(occupancyPercentage(10, 0)).toBe(0);
    expect(occupancyPercentage(-1, 10)).toBe(0);
    expect(occupancyPercentage(12, 10)).toBe(100);
  });
});
