import { Fragment } from "react";

export function BoldDescription({ text }: { text: string }) {
  return <>{text.split(/(\*\*.+?\*\*)/gs).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>
  )}</>;
}
