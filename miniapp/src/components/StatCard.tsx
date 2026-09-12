import { Paper, Text } from "@mantine/core";
import type { ReactNode } from "react";
import "./StatCard.css";

export function StatCard({ label, value }: { label: string; value: ReactNode }) {
  return <Paper className="resource-card stat-card">
    <Text size="sm" c="dimmed">{label}</Text>
    <Text className="stat-card-value">{value}</Text>
  </Paper>;
}
