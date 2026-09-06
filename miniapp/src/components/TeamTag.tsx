import { Badge } from "@mantine/core";

export const teamColors = ["blue", "cyan", "teal", "green", "grape", "violet", "orange", "pink"] as const;
export type TeamColor = typeof teamColors[number];

export function teamColor(teamName: string): TeamColor {
  let hash = 0;
  for (const character of teamName.trim().toLocaleLowerCase("ru")) {
    hash = ((hash << 5) - hash + (character.codePointAt(0) ?? 0)) | 0;
  }
  return teamColors[Math.abs(hash) % teamColors.length];
}

export function TeamTag({ name }: { name: string }) {
  return <Badge color={teamColor(name)} variant="light" radius="sm">{name}</Badge>;
}
