import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { decode as decodePng, encode as encodePng } from "fast-png";
import { exportDiagram } from "./diagram-export";

const PNG_BYTES = encodePng({
  width: 1,
  height: 1,
  channels: 4,
  data: new Uint8Array([255, 0, 0, 255]),
});
const PNG_DATA_URL = `data:image/png;base64,${btoa(String.fromCharCode(...PNG_BYTES))}`;
const urlCreateDescriptor = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
const urlRevokeDescriptor = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
const canvasGetContextDescriptor = Object.getOwnPropertyDescriptor(
  HTMLCanvasElement.prototype,
  "getContext",
);
const canvasToBlobDescriptor = Object.getOwnPropertyDescriptor(
  HTMLCanvasElement.prototype,
  "toBlob",
);
const canvasToDataURLDescriptor = Object.getOwnPropertyDescriptor(
  HTMLCanvasElement.prototype,
  "toDataURL",
);

let outputBlobs: Blob[];

function readBlob(blob: Blob, readAs: "text"): Promise<string>;
function readBlob(blob: Blob, readAs: "arrayBuffer"): Promise<ArrayBuffer>;
function readBlob(blob: Blob, readAs: "text" | "arrayBuffer") {
  return new Promise<string | ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string | ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    if (readAs === "text") reader.readAsText(blob);
    else reader.readAsArrayBuffer(blob);
  });
}

function restoreDescriptor(
  target: object,
  key: PropertyKey,
  descriptor: PropertyDescriptor | undefined,
) {
  if (descriptor) Object.defineProperty(target, key, descriptor);
  else Reflect.deleteProperty(target, key);
}

function installDownloadStubs() {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn((blob: Blob) => {
      outputBlobs.push(blob);
      return `blob:export-${outputBlobs.length}`;
    }),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  vi.spyOn(globalThis, "setTimeout").mockImplementation(() => 0 as never);
}

function installRasterStubs() {
  class ImmediateImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(_value: string) {
      queueMicrotask(() => this.onload?.());
    }
  }
  vi.stubGlobal("Image", ImmediateImage);
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    configurable: true,
    value: vi.fn(() => ({ drawImage: vi.fn() })),
  });
  Object.defineProperty(HTMLCanvasElement.prototype, "toBlob", {
    configurable: true,
    value: vi.fn((callback: BlobCallback) => {
      const pngBuffer = new Uint8Array(PNG_BYTES).buffer as ArrayBuffer;
      callback(new Blob([pngBuffer], { type: "image/png" }));
    }),
  });
  Object.defineProperty(HTMLCanvasElement.prototype, "toDataURL", {
    configurable: true,
    value: vi.fn(() => PNG_DATA_URL),
  });
}

describe("diagram export serialization", () => {
  beforeEach(() => {
    outputBlobs = [];
    document.body.innerHTML =
      '<svg id="process-diagram" viewBox="0 0 100 60"><rect x="1" y="2" width="20" height="10" /></svg>';
    installDownloadStubs();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    restoreDescriptor(URL, "createObjectURL", urlCreateDescriptor);
    restoreDescriptor(URL, "revokeObjectURL", urlRevokeDescriptor);
    restoreDescriptor(HTMLCanvasElement.prototype, "getContext", canvasGetContextDescriptor);
    restoreDescriptor(HTMLCanvasElement.prototype, "toBlob", canvasToBlobDescriptor);
    restoreDescriptor(HTMLCanvasElement.prototype, "toDataURL", canvasToDataURLDescriptor);
    document.body.replaceChildren();
  });

  it("downloads non-empty, parseable SVG markup", async () => {
    await exportDiagram("SVG");
    expect(outputBlobs).toHaveLength(1);
    const svgBlob = outputBlobs[0]!;
    expect(svgBlob.type).toBe("image/svg+xml");
    expect(svgBlob.size).toBeGreaterThan(0);
    const parsed = new DOMParser().parseFromString(
      await readBlob(svgBlob, "text"),
      "image/svg+xml",
    );
    expect(parsed.querySelector("parsererror")).toBeNull();
    expect(parsed.documentElement.localName).toBe("svg");
    expect(parsed.querySelector("rect")).not.toBeNull();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
  });

  it("passes a non-empty PNG with its signature to the download URL", async () => {
    installRasterStubs();
    await exportDiagram("PNG");
    const png = outputBlobs[1]!;
    expect(png.type).toBe("image/png");
    expect(png.size).toBeGreaterThan(8);
    const decoded = decodePng(await readBlob(png, "arrayBuffer"));
    expect(decoded.width).toBe(1);
    expect(decoded.height).toBe(1);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
  });

  it("produces a non-empty PDF with a PDF header and end marker", async () => {
    installRasterStubs();
    await exportDiagram("PDF");
    const pdf = outputBlobs[1]!;
    expect(pdf.type).toBe("application/pdf");
    const bytes = new Uint8Array(await readBlob(pdf, "arrayBuffer"));
    const content = new TextDecoder().decode(bytes);
    expect(content.startsWith("%PDF-")).toBe(true);
    expect(content).toContain("%%EOF");
    expect(pdf.size).toBeGreaterThan(100);
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
  });
});
