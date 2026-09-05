import type { ReactNode } from "react";

export function BottomActionBar({ children, navigation = false }: { children: ReactNode; navigation?: boolean }) {
  return <div className={`bottom-action-bar${navigation ? " bottom-action-navigation" : ""}`}>{children}</div>;
}

export function BottomNavAction({ icon, label, meta, onClick }: { icon: string; label: string; meta?: number | string; onClick: () => void }) {
  return <button type="button" className="bottom-nav-action" onClick={onClick}>
    <span className="bottom-nav-icon" aria-hidden="true">{icon}</span>
    <span>{label}</span>
    {meta !== undefined && <span className="bottom-nav-meta">{meta}</span>}
  </button>;
}
