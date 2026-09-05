import type { ReactNode } from "react";

export type TabBarIconName = "shows" | "create" | "settings" | "attendees" | "edit" | "announce" | "analytics" | "more";

function TabBarIcon({ name }: { name: TabBarIconName }) {
  const paths: Record<TabBarIconName, ReactNode> = {
    shows: <><rect x="3.5" y="4.5" width="17" height="16" rx="3" /><path d="M7.5 2.8v3.4M16.5 2.8v3.4M3.5 9h17M7.5 13h3M7.5 16.5h6" /></>,
    create: <><circle cx="12" cy="12" r="9" /><path d="M12 8v8M8 12h8" /></>,
    settings: <><circle cx="12" cy="12" r="3.2" /><path d="M19.4 13.5a7.8 7.8 0 0 0 0-3l1.7-1.3-2-3.4-2 .8a8 8 0 0 0-2.6-1.5L14.2 3h-4.4l-.3 2.1a8 8 0 0 0-2.6 1.5l-2-.8-2 3.4 1.7 1.3a7.8 7.8 0 0 0 0 3l-1.7 1.3 2 3.4 2-.8a8 8 0 0 0 2.6 1.5l.3 2.1h4.4l.3-2.1a8 8 0 0 0 2.6-1.5l2 .8 2-3.4-1.7-1.3Z" /></>,
    attendees: <><path d="M8.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 20v-2a6 6 0 0 1 12 0v2" /><path d="M16 11a3 3 0 0 0 0-5.8M16 14a5 5 0 0 1 5 5v1" /></>,
    edit: <><path d="M4 20h4l11-11a2.8 2.8 0 0 0-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4M4 20h16" /></>,
    announce: <><path d="M4 13V9h4l9-4v12l-9-4H4Z" /><path d="m8 13 1.5 6h3L11 14M20 8.5a5 5 0 0 1 0 5" /></>,
    analytics: <><path d="M4 20V11M10 20V4M16 20v-6M22 20V8" /><path d="M2 20h22" /></>,
    more: <><circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1.4" fill="currentColor" stroke="none" /></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

export function BottomActionBar({ children, navigation = false, inline = false }: { children: ReactNode; navigation?: boolean; inline?: boolean }) {
  return <div className={`bottom-action-bar${navigation ? " bottom-action-navigation" : ""}${inline ? " is-inline" : ""}`}>{children}</div>;
}

export function BottomNavAction({ icon, label, meta, active = false, onClick }: { icon: TabBarIconName; label: string; meta?: number | string; active?: boolean; onClick: () => void }) {
  return <button type="button" className={`bottom-nav-action${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined} onClick={onClick}>
    <span className="bottom-nav-icon"><TabBarIcon name={icon} /></span>
    <span className="bottom-nav-label">{label}</span>
    {meta !== undefined && <span className="bottom-nav-meta">{meta}</span>}
  </button>;
}

export function RootNavigation({ onShows, onCreate, onSettings }: { onShows: () => void; onCreate: () => void; onSettings: () => void }) {
  return <BottomActionBar navigation>
    <BottomNavAction icon="shows" label="Афиши" active onClick={onShows} />
    <BottomNavAction icon="create" label="Создать" onClick={onCreate} />
    <BottomNavAction icon="settings" label="Настройки" onClick={onSettings} />
  </BottomActionBar>;
}
