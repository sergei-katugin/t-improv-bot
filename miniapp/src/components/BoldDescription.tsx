import { Fragment } from "react";

export const BOLD_FRAGMENT_PATTERN = /(\*\*[\s\S]+?\*\*)/g;

export function BoldDescription({ text }: { text: string }) {
  return <>{text.split(BOLD_FRAGMENT_PATTERN).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>
  )}</>;
}
