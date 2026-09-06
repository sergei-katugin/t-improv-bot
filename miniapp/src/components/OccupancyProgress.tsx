import { Progress } from "@mantine/core";

export type OccupancyColor = "red" | "orange" | "blue" | "green";

export function occupancyPercentage(occupied: number, capacity: number): number {
  if (capacity <= 0) return 0;
  return Math.max(0, Math.min(100, occupied / capacity * 100));
}

export function occupancyColor(percentage: number): OccupancyColor {
  if (percentage < 25) return "red";
  if (percentage < 50) return "orange";
  if (percentage < 75) return "blue";
  return "green";
}

export function OccupancyProgress({ occupied, capacity, mt = 8 }: { occupied: number; capacity: number; mt?: number | string }) {
  const value = occupancyPercentage(occupied, capacity);
  return <Progress value={value} color={occupancyColor(value)} mt={mt} aria-label={`Заполнено ${Math.round(value)}%`} />;
}
