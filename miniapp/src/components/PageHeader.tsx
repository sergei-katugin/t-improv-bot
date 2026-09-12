import type { ReactNode } from "react";
import "./PageHeader.css";

export function PageHeader({ title, subtitle }: { title: string; subtitle?: ReactNode }) {
  return <header className="page-header">
    <h1 title={title}>{title}</h1>
    {subtitle && <div className="page-header-subtitle">{subtitle}</div>}
  </header>;
}
