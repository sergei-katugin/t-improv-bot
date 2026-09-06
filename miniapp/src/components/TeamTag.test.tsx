import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TeamTag, teamColor, teamColors } from "./TeamTag";

describe("teamColor", () => {
  it("is stable for the same normalized team name", () => {
    expect(teamColor("Экспериментаторы")).toBe(teamColor("  ЭКСПЕРИМЕНТАТОРЫ "));
  });

  it("always returns a theme palette color", () => {
    expect(teamColors).toContain(teamColor("Другая команда"));
  });
});

describe("TeamTag", () => {
  it("renders the team as a tag", () => {
    render(<MantineProvider><TeamTag name="Экспериментаторы" /></MantineProvider>);
    expect(screen.getByText("Экспериментаторы")).toBeInTheDocument();
  });
});
