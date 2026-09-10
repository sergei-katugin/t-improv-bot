import React from "react";

import { authenticatedBlob } from "../lib/api";


export function PosterPreviewImage({ file, showId, hasExisting }: {
  file: File | null;
  showId?: number;
  hasExisting?: boolean;
}) {
  const [source, setSource] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    const showBlob = (blob: Blob) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setSource(objectUrl);
    };
    setSource(null);
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        if (active && typeof reader.result === "string") setSource(reader.result);
      };
      reader.readAsDataURL(file);
      return () => { active = false; reader.abort(); };
    }
    if (showId && hasExisting) {
      void authenticatedBlob(`/api/miniapp/shows/${showId}/poster`)
        .then(showBlob)
        .catch(() => undefined);
    }
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [file, hasExisting, showId]);

  return source
    ? <img className="telegram-preview-poster" src={source} alt="Изображение афиши в предпросмотре" />
    : null;
}
