import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getSavedRun,
  getSavedRunFile,
  listSavedRuns,
  processPid,
} from "./untangle-api";

describe("saved run API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the run list and a run by its stable ID", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ runs: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ run_id: "run-123" }), { status: 200 }));

    await expect(listSavedRuns("token")).resolves.toEqual({ runs: [] });
    await expect(getSavedRun("run-123", "token")).resolves.toMatchObject({ run_id: "run-123" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://localhost:8000/api/runs?limit=20");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("http://localhost:8000/api/runs/run-123");
  });

  it("retrieves a saved PDF as a Blob for source preview restoration", async () => {
    const pdf = new Blob(["%PDF-1.4\n"], { type: "application/pdf" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(pdf, { status: 200 }));

    await expect(getSavedRunFile("run-123", "pdf", "token")).resolves.toBeInstanceOf(Blob);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://localhost:8000/api/runs/run-123/files/pdf");
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).headers).toEqual({ Authorization: "Bearer token" });
  });

  it("posts the expected upload fields and surfaces the backend OCR error", async () => {
    const detail =
      "Install Tesseract OCR in Windows PowerShell with `winget install --id UB-Mannheim.TesseractOCR -e`.";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const pdf = new File(["%PDF-1.4"], "drawing.pdf", { type: "application/pdf" });
    const excel = new File(["workbook"], "inventory.xlsx");

    await expect(processPid(pdf, excel, "token")).rejects.toMatchObject({
      message: detail,
      status: 400,
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://localhost:8000/api/process-pid");
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = request.body as FormData;
    expect(body.get("file_pdf")).toBe(pdf);
    expect(body.get("file_excel")).toBe(excel);
    expect(body.get("demo_mode")).toBeNull();
  });
});
