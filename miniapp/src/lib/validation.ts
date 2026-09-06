export function invalidTelegramUsername(raw: string): string | null {
  const usernames = raw.split(/[,;\n]+/).map((item) => item.trim()).filter(Boolean);
  return usernames.find((item) => {
    const username = item.replace(/^https?:\/\/t\.me\//i, "").replace(/^@/, "").replace(/[/?#].*$/, "");
    return !/^[A-Za-z0-9_]{5,32}$/.test(username);
  }) ?? null;
}
