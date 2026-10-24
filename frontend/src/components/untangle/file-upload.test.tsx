import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FileUploadDropzone } from "./file-upload";

describe("FileUploadDropzone authentication gate", () => {
  it("explains unsupported files dropped into the upload area", () => {
    const { container } = render(
      <FileUploadDropzone processing={false} onProcess={vi.fn()} onPdfSelected={vi.fn()} />,
    );
    const dropzone = container.querySelector(".upload-dropzone");
    if (!dropzone) throw new Error("Upload dropzone was not rendered");

    fireEvent.drop(dropzone, {
      dataTransfer: { files: [new File(["not a drawing"], "drawing.png")] },
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Choose a P&ID PDF or an Excel workbook");
  });

  it("locks upload controls until sign-in is requested", () => {
    const onRequestLogin = vi.fn();
    const { container } = render(
      <FileUploadDropzone
        processing={false}
        onProcess={vi.fn()}
        onPdfSelected={vi.fn()}
        locked
        onRequestLogin={onRequestLogin}
      />,
    );

    expect(screen.getByRole("button", { name: "Select P&ID PDF" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Select I/O Excel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate simplified PFD" })).toBeDisabled();
    expect(
      Array.from(container.querySelectorAll<HTMLInputElement>('input[type="file"]')).every(
        (input) => input.disabled,
      ),
    ).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(onRequestLogin).toHaveBeenCalledOnce();
  });
});
