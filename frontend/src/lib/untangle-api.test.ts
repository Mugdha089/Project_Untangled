import { afterEach, describe, expect, it, vi } from "vitest";
import { getSavedRun, getSavedRunFile, listSavedRuns } from "./untangle-api";

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
});
