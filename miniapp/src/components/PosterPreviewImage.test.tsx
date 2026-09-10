import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { PosterPreviewImage } from "./PosterPreviewImage";


it("shows a selected local poster as a WebView-compatible data URL", async () => {
  const file = new File(["image"], "poster.jpg", { type: "image/jpeg" });

  render(<PosterPreviewImage file={file} />);

  expect(await screen.findByRole("img", { name: "Изображение афиши в предпросмотре" }))
    .toHaveAttribute("src", expect.stringMatching(/^data:image\/jpeg;base64,/));
});
