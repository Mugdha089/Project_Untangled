import { useCallback, useRef, useState, type DragEvent } from "react";
import { FileSpreadsheet, FileText, Loader2, LockKeyhole, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

interface FileUploadProps {
  processing: boolean;
  onProcess: (pdf: File, excel: File) => Promise<void> | void;
  onPdfSelected: (pdf: File) => void;
  locked?: boolean;
  onRequestLogin?: () => void;
  pdfName?: string;
  excelName?: string;
}

export function FileUploadDropzone({
  processing,
  onProcess,
  onPdfSelected,
  locked = false,
  onRequestLogin,
  pdfName,
  excelName,
}: FileUploadProps) {
  const pdfRef = useRef<HTMLInputElement>(null);
  const excelRef = useRef<HTMLInputElement>(null);
  const [pdf, setPdf] = useState<File | null>(null);
  const [excel, setExcel] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const assignFile = useCallback(
    (file: File) => {
      if (locked) return;
      const lower = file.name.toLowerCase();
      if (lower.endsWith(".pdf")) {
        setPdf(file);
        onPdfSelected(file);
      } else if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) setExcel(file);
    },
    [locked, onPdfSelected],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragOver(false);
      Array.from(event.dataTransfer.files).forEach(assignFile);
    },
    [assignFile],
  );

  const canSubmit = Boolean(pdf && excel) && !processing && !locked;

  return (
    <section
      className={`upload-panel ${locked ? "upload-auth-lock" : ""}`}
      aria-label="Upload P&ID and I/O list"
    >
      <div
        className={`upload-dropzone ${dragOver ? "is-dragover" : ""} ${processing ? "is-processing" : ""}`}
        onDragOver={(e) => {
          if (locked) return;
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <div className="upload-icon">
          {processing ? <Loader2 className="spin" size={22} /> : <Upload size={22} />}
        </div>
        <div className="upload-copy">
          <h2>Upload P&ID PDF + I/O Excel</h2>
          <p>
            Drop files here or browse. Both a <strong>.pdf</strong> blueprint and an{" "}
            <strong>.xlsx</strong> tag sheet are required.
          </p>
        </div>
        <div className="upload-file-row">
          <button
            type="button"
            className={`upload-file-chip ${pdf ? "has-file" : ""}`}
            onClick={() => pdfRef.current?.click()}
            disabled={processing || locked}
          >
            <FileText size={14} />
            <span>{pdf?.name ?? pdfName ?? "Select P&ID PDF"}</span>
          </button>
          <button
            type="button"
            className={`upload-file-chip ${excel ? "has-file" : ""}`}
            onClick={() => excelRef.current?.click()}
            disabled={processing || locked}
          >
            <FileSpreadsheet size={14} />
            <span>{excel?.name ?? excelName ?? "Select I/O Excel"}</span>
          </button>
        </div>
        <Button
          className="upload-submit"
          disabled={!canSubmit}
          onClick={() => {
            if (pdf && excel) void onProcess(pdf, excel);
          }}
        >
          {processing ? (
            <>
              <Loader2 className="spin" size={15} />
              Processing…
            </>
          ) : (
            <>
              <Upload size={15} />
              Generate simplified PFD
            </>
          )}
        </Button>
        <input
          ref={pdfRef}
          type="file"
          accept=".pdf,application/pdf"
          className="sr-only"
          disabled={locked || processing}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) assignFile(file);
          }}
        />
        <input
          ref={excelRef}
          type="file"
          accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="sr-only"
          disabled={locked || processing}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) setExcel(file);
          }}
        />
      </div>
      {locked && (
        <div className="upload-auth-gate">
          <LockKeyhole size={16} />
          <span>Sign in to unlock the workspace</span>
          <Button size="sm" onClick={onRequestLogin}>
            Sign in
          </Button>
        </div>
      )}
    </section>
  );
}
