export function ChevronRight({ className = "" }: { className?: string }) {
  return <svg className={`ios-chevron${className ? ` ${className}` : ""}`} viewBox="0 0 12 20" aria-hidden="true">
    <path d="m2 2 8 8-8 8" />
  </svg>;
}
