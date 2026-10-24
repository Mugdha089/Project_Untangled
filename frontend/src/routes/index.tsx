import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowRight,
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CircleHelp,
  Crosshair,
  Download,
  FileText,
  GitBranch,
  Layers,
  Link2,
  Loader2,
  LogOut,
  Maximize2,
  Minus,
  Network,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Timer,
  TriangleAlert,
  X,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ProcessDiagram, SourceDiagram, IntersectionCrop } from "@/components/untangle/diagrams";
import { FileUploadDropzone } from "@/components/untangle/file-upload";
import { AuthModal, type AuthUser } from "@/components/auth-modal";
import {
  auditTags as demoAuditTags,
  clarifications as demoClarifications,
  defaultGraphEdges,
  defaultGraphNodes,
  mapGraphEdges,
  mapGraphNodes,
  mapProcessResponse,
  markTagUserConfirmed,
  metrics as demoMetrics,
  resolutionToOption,
  resolveQueue,
  type AuditStatus,
  type AuditTag,
  type ClarificationView,
  type EquipmentId,
  type GraphEdgeView,
  type GraphNodeView,
  type Resolution,
  type WorkspaceMetrics,
} from "@/lib/untangle-data";
import {
  getSavedRun,
  getSavedRunFile,
  getCurrentUser,
  listSavedRuns,
  processPid,
  resolveAmbiguities,
  type SavedRunSummary,
  UntangleApiError,
} from "@/lib/untangle-api";
import { exportDiagram } from "@/lib/diagram-export";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "UNTANGLE — P&ID Digitisation Workspace" },
      {
        name: "description",
        content:
          "Project UNTANGLE engineering workspace for traceable P&ID digitisation, process simplification, and tag completeness auditing.",
      },
      { property: "og:title", content: "UNTANGLE — P&ID Digitisation Workspace" },
      {
        property: "og:description",
        content:
          "Explore linked engineering diagrams, validate process topology, and resolve ambiguous connections.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const statusLabels: Record<AuditStatus, string> = {
  matched: "Matched",
  missing: "Missing in P&ID",
  pending: "Pending review",
  ambiguous: "Ambiguous",
  "user-confirmed": "User-confirmed (session)",
};

const AUTH_TOKEN_STORAGE_KEY = "untangle.auth.token";
const LAST_RUN_STORAGE_KEY = "untangle.lastRunId";

function initialsForName(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

function Index() {
  const [selected, setSelected] = useState<EquipmentId | null>(null);
  const [hovered, setHovered] = useState<EquipmentId | null>(null);
  const [boxes, setBoxes] = useState(true);
  const [zoom, setZoom] = useState(100);
  const [view, setView] = useState("pfd");
  const [pfdZoom, setPfdZoom] = useState<"auto" | "fit" | number>("auto");
  const [pfdFitScale, setPfdFitScale] = useState(1);
  const [pfdAutoScale, setPfdAutoScale] = useState(1);
  const [auditOpen, setAuditOpen] = useState(true);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [workspaceMetrics, setWorkspaceMetrics] = useState<WorkspaceMetrics>(demoMetrics);
  const [auditRows, setAuditRows] = useState<AuditTag[]>(demoAuditTags);
  const [graphNodes, setGraphNodes] = useState<GraphNodeView[]>(defaultGraphNodes);
  const [graphEdges, setGraphEdges] = useState<GraphEdgeView[]>(defaultGraphEdges);
  const [queue, setQueue] = useState<ClarificationView[]>(demoClarifications);
  const [queueOpen, setQueueOpen] = useState(false);
  const [queueIndex, setQueueIndex] = useState(0);
  const [resolution, setResolution] = useState<Resolution>("bridge");
  const [selectedOption, setSelectedOption] = useState<string>("");
  const [answerDrafts, setAnswerDrafts] = useState<Record<string, string>>({});
  const [userConfirmedTags, setUserConfirmedTags] = useState<string[]>([]);
  const [locatingTag, setLocatingTag] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [notice, setNotice] = useState("");
  const [expanded, setExpanded] = useState<"source" | "pfd" | null>(null);
  const [exporting, setExporting] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [restoringRun, setRestoringRun] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [projectName, setProjectName] = useState("Project_Alpha_4K_Sheet_01.pdf");
  const [excelName, setExcelName] = useState("Project_Alpha_IO_List.xlsx");
  const [pdfPageCount, setPdfPageCount] = useState(1);
  const [liveConnected, setLiveConnected] = useState(false);
  const [sourcePdf, setSourcePdf] = useState<File | null>(null);
  const [sourcePdfUrl, setSourcePdfUrl] = useState<string | null>(null);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [savedRuns, setSavedRuns] = useState<SavedRunSummary[]>([]);
  const runRequestToken = useRef(0);

  const clearAuthenticatedWorkspace = useCallback(() => {
    runRequestToken.current += 1;
    setCurrentRunId(null);
    setLiveConnected(false);
    setSourcePdf(null);
    setAuditRows(demoAuditTags);
    setGraphNodes(defaultGraphNodes);
    setGraphEdges(defaultGraphEdges);
    setQueue(demoClarifications);
    setWorkspaceMetrics(demoMetrics);
    setUserConfirmedTags([]);
    setSavedRuns([]);
    setAnswerDrafts({});
  }, []);

  const updatePfdScales = useCallback((fitScale: number, autoScale: number) => {
    setPfdFitScale(fitScale);
    setPfdAutoScale(autoScale);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 4500);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  useEffect(() => {
    let cancelled = false;
    try {
      const token = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
      if (!token) {
        setAuthReady(true);
        return;
      }
      void getCurrentUser(token)
        .then((user) => {
          if (cancelled) return;
          setAuthToken(token);
          setAuthUser({
            userId: user.user_id,
            fullName: user.full_name,
            email: user.email,
            role: user.role,
          });
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
            setAuthUser(null);
            if (error instanceof UntangleApiError && error.status === 401) {
              toast.error("Session expired", {
                description: "Sign in again to access saved runs.",
              });
            }
          }
        })
        .finally(() => {
          if (!cancelled) setAuthReady(true);
        });
    } catch (error) {
      console.error("Unable to restore the UNTANGLE session.", error);
      setAuthReady(true);
    }
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onExpired = () => {
      localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      setAuthToken(null);
      setAuthUser(null);
      clearAuthenticatedWorkspace();
      toast.error("Session expired", { description: "Sign in again to continue." });
    };
    window.addEventListener("untangle:auth-expired", onExpired);
    return () => window.removeEventListener("untangle:auth-expired", onExpired);
  }, [clearAuthenticatedWorkspace]);

  useEffect(() => {
    if (!sourcePdf) {
      setSourcePdfUrl(null);
      return;
    }

    const url = URL.createObjectURL(sourcePdf);
    setSourcePdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [sourcePdf]);

  useEffect(() => {
    if (!authToken) return;
    let cancelled = false;
    const token = ++runRequestToken.current;
    let savedRunId: string | null = null;
    try {
      savedRunId = localStorage.getItem(LAST_RUN_STORAGE_KEY);
    } catch (error) {
      console.error("Unable to read the saved UNTANGLE run ID.", error);
    }
    if (!savedRunId) return;

    void (async () => {
      try {
        const response = await getSavedRun(savedRunId, authToken);
        if (cancelled || token !== runRequestToken.current) return;
        const mapped = mapProcessResponse(response);
        setCurrentRunId(mapped.runId);
        setWorkspaceMetrics(mapped.metrics);
        setAuditRows(mapped.auditTags);
        setGraphNodes(mapped.graphNodes);
        setGraphEdges(mapped.graphEdges);
        setQueue(mapped.clarifications);
        setPdfPageCount(mapped.pdfPageCount);
        setProjectName(mapped.pdfFilename);
        setExcelName(mapped.excelFilename);
        setUserConfirmedTags([]);
        setLiveConnected(true);
        setQueueIndex(0);
        setResolution("bridge");
        setSelectedOption(mapped.clarifications[0]?.selectedOption ?? "");
        if (mapped.clarifications.length) setQueueOpen(true);

        try {
          const pdf = await getSavedRunFile(mapped.runId, "pdf", authToken);
          if (!cancelled && token === runRequestToken.current) {
            setSourcePdf(new File([pdf], mapped.pdfFilename, { type: "application/pdf" }));
          }
        } catch (error) {
          console.error("Saved run was restored, but its source PDF could not be loaded.", error);
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Unable to restore the last saved UNTANGLE run.", error);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authToken]);

  useEffect(() => {
    if (!authToken) {
      setSavedRuns([]);
      return;
    }
    let cancelled = false;
    void listSavedRuns(authToken)
      .then((result) => {
        if (!cancelled) setSavedRuns(result.runs);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          console.error("Unable to load saved UNTANGLE runs.", error);
          toast.error("Saved runs unavailable", {
            description:
              error instanceof Error ? error.message : "The run list could not be loaded.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authToken]);

  const active = hovered ?? selected;
  const current = queue[queueIndex];
  const activeOption = (current ? answerDrafts[current.id] : undefined) ?? selectedOption;

  const tags = useMemo(
    () =>
      userConfirmedTags.reduce((rows, tagName) => markTagUserConfirmed(rows, tagName), auditRows),
    [auditRows, userConfirmedTags],
  );

  const matchedCount = tags.filter((t) => t.status === "matched").length;
  const missingCount = tags.filter((t) => t.status === "missing").length;
  const pendingCount = tags.filter((t) => t.status === "pending").length;
  const ambiguousCount = tags.filter((t) => t.status === "ambiguous").length;
  const userConfirmedCount = tags.filter((t) => t.status === "user-confirmed").length;
  const completeness =
    workspaceMetrics.total > 0
      ? ((workspaceMetrics.matched / workspaceMetrics.total) * 100).toFixed(1)
      : "0.0";

  const filtered = tags.filter(
    (t) =>
      (filter === "all" || t.status === filter) &&
      `${t.tag} ${t.type}`.toLowerCase().includes(search.toLowerCase()),
  );

  const notify = (text: string) => {
    setNotice(text);
  };

  const handleLogout = () => {
    try {
      localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    } catch (error) {
      console.error("Unable to clear the local UNTANGLE session.", error);
      toast.error("Could not clear saved session", {
        description:
          "Your workspace has been locked for this session, but browser storage could not be updated.",
      });
    }
    setAuthUser(null);
    setAuthToken(null);
    clearAuthenticatedWorkspace();
    toast.success("Signed out");
  };

  const showApiError = (error: unknown) => {
    if (error instanceof UntangleApiError) {
      toast.error(error.unreachable ? "Server unreachable" : "Request failed", {
        description: error.message,
        id: "untangle-api-error",
      });
      return;
    }
    const message =
      error instanceof Error ? error.message : "Unexpected error talking to the backend.";
    toast.error("Request failed", { description: message, id: "untangle-api-error" });
  };

  const handleProcess = async (pdf: File, excel: File) => {
    runRequestToken.current += 1;
    setProcessing(true);
    try {
      if (!authToken) throw new Error("Sign in to process a drawing.");
      const response = await processPid(pdf, excel, authToken);
      const mapped = mapProcessResponse(response);
      setCurrentRunId(mapped.runId);
      setSavedRuns((runs) =>
        [
          {
            run_id: response.run_id,
            created_at: response.created_at,
            pdf_filename: response.pdf_filename,
            excel_filename: response.excel_filename,
            kpis: response.kpis,
          },
          ...runs.filter((run) => run.run_id !== response.run_id),
        ].slice(0, 20),
      );
      try {
        localStorage.setItem(LAST_RUN_STORAGE_KEY, mapped.runId);
      } catch (error) {
        console.error("Unable to remember the last saved run in this browser.", error);
      }
      setSourcePdf(pdf);
      setWorkspaceMetrics(mapped.metrics);
      setAuditRows(mapped.auditTags);
      setGraphNodes(mapped.graphNodes);
      setGraphEdges(mapped.graphEdges);
      setQueue(mapped.clarifications);
      setPdfPageCount(mapped.pdfPageCount);
      setProjectName(pdf.name);
      setExcelName(excel.name);
      setUserConfirmedTags([]);
      setLocatingTag(null);
      setPfdZoom("auto");
      setLiveConnected(true);
      setQueueIndex(0);
      setResolution("bridge");
      setSelectedOption("");
      setAnswerDrafts({});
      toast.success("P&ID processed", {
        description: `${mapped.metrics.matched}/${mapped.metrics.total} tags matched in ${mapped.metrics.seconds}s`,
        id: "untangle-process",
      });
      if (mapped.clarifications.length) setQueueOpen(true);
    } catch (error) {
      showApiError(error);
    } finally {
      setProcessing(false);
    }
  };

  const openSavedRun = async (runId: string) => {
    if (!authToken) return;
    setRestoringRun(true);
    try {
      const response = await getSavedRun(runId, authToken);
      const mapped = mapProcessResponse(response);
      setCurrentRunId(mapped.runId);
      try {
        localStorage.setItem(LAST_RUN_STORAGE_KEY, mapped.runId);
      } catch (error) {
        console.error("Unable to remember the selected saved run.", error);
      }
      setWorkspaceMetrics(mapped.metrics);
      setAuditRows(mapped.auditTags);
      setGraphNodes(mapped.graphNodes);
      setGraphEdges(mapped.graphEdges);
      setQueue(mapped.clarifications);
      setPdfPageCount(mapped.pdfPageCount);
      setProjectName(mapped.pdfFilename);
      setExcelName(mapped.excelFilename);
      setUserConfirmedTags([]);
      setLiveConnected(true);
      setQueueIndex(0);
      setSelectedOption(mapped.clarifications[0]?.selectedOption ?? "");
      setAnswerDrafts({});
      setQueueOpen(mapped.clarifications.length > 0);
      const pdf = await getSavedRunFile(mapped.runId, "pdf", authToken);
      setSourcePdf(new File([pdf], mapped.pdfFilename, { type: "application/pdf" }));
      toast.success("Saved run opened", { description: mapped.pdfFilename });
    } catch (error) {
      showApiError(error);
    } finally {
      setRestoringRun(false);
    }
  };

  const confirmLocatedTag = (tagName: string) => {
    setAuditRows((rows) => markTagUserConfirmed(rows, tagName));
    setUserConfirmedTags((tags) => (tags.includes(tagName) ? tags : [...tags, tagName]));
    setLocatingTag(null);
    setLocating(false);
    notify(
      `${tagName} marked user-confirmed for this session. Backend detection status is unchanged.`,
    );
  };

  const selectSource = (id: EquipmentId) => {
    setSelected(id);
    if (locatingTag && !sourcePdfUrl) {
      confirmLocatedTag(locatingTag);
    }
  };

  const openQueue = () => {
    setQueueIndex(0);
    setResolution("bridge");
    setSelectedOption(queue[0]?.selectedOption ?? "");
    setQueueOpen(true);
  };

  const applyResolution = async () => {
    if (!current) return;
    const answers = Object.entries(answerDrafts).map(([item_id, selected_option]) => ({
      item_id,
      selected_option,
    }));
    if (!answers.length && liveConnected) {
      toast.error("No answers selected", {
        description: "Choose an option for at least one question before updating the diagram.",
      });
      return;
    }
    const option = activeOption || resolutionToOption(current, "bridge");
    setResolving(true);
    try {
      if (liveConnected) {
        if (!currentRunId) throw new Error("The saved run ID is unavailable.");
        if (!authToken) throw new Error("Sign in to resolve clarifications.");
        const result = await resolveAmbiguities(currentRunId, answers, authToken);
        const mapped = mapProcessResponse(result);
        setWorkspaceMetrics(mapped.metrics);
        setAuditRows(mapped.auditTags);
        setGraphNodes(mapped.graphNodes);
        setGraphEdges(mapped.graphEdges);
        setQueue(mapped.clarifications);
        setQueueIndex(0);
        setSelectedOption(mapped.clarifications[0]?.selectedOption ?? "");
        setAnswerDrafts({});
        toast.success("Clarification recorded", {
          description: "Selected answers were saved together and the affected graph was updated.",
          id: "untangle-clarification",
        });
        if (!mapped.clarifications.length) setQueueOpen(false);
      } else {
        notify(
          resolution === "unresolved"
            ? "Intersection kept flagged for review."
            : `Intersection #${String(current.id).padStart(2, "0")} resolved. Source topology remains unverified.`,
        );
        const next = resolveQueue(queue, current.id, option);
        setQueue(next);
        setQueueIndex(0);
        setResolution("bridge");
        setSelectedOption(next[0] ? resolutionToOption(next[0], "bridge") : "");
        if (!next.length) setQueueOpen(false);
      }
    } catch (error) {
      showApiError(error);
    } finally {
      setResolving(false);
    }
  };

  const handleExport = async (format: "SVG" | "PNG" | "PDF") => {
    setExporting(true);
    try {
      await exportDiagram(format);
      notify(`${format} diagram exported.`);
    } catch (error) {
      toast.error("Diagram export failed", {
        description: error instanceof Error ? error.message : "Export failed. Please try again.",
        id: "untangle-export-error",
      });
    } finally {
      setExporting(false);
    }
  };

  const changePfdZoom = (direction: -1 | 1) => {
    setPfdZoom((current) => {
      const scale =
        current === "auto" ? pfdAutoScale : current === "fit" ? pfdFitScale : current / 100;
      return Math.max(30, Math.min(200, Math.round(scale * 100) + direction * 10));
    });
  };

  const auditTable = (compact = false) => (
    <div className={`table-scroll ${compact ? "compact-audit" : ""}`}>
      <table>
        <thead>
          <tr>
            <th>TAG NAME</th>
            <th>TYPE</th>
            <th>SOURCE BOUNDING BOX</th>
            <th>EXCEL ROW(S)</th>
            <th>STATUS</th>
            <th className="action-heading">ACTION</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((tag) => (
            <tr key={tag.tag} className={selected === tag.equipment ? "selected-row" : ""}>
              <td>
                <span className="tag-cell">
                  <span className={`status-dot ${tag.status}`} />
                  {tag.tag}
                </span>
                {tag.ocrConfidence !== undefined && (
                  <small className="mono muted-text">
                    OCR: {tag.rawText ?? tag.tag} · {Math.round(tag.ocrConfidence)}%
                  </small>
                )}
                {tag.reason && (
                  <small className="muted-text">{tag.reason}</small>
                )}
              </td>
              <td>{tag.type}</td>
              <td className={`mono bounds ${tag.status === "missing" ? "muted-text" : ""}`}>
                {tag.bounds}
              </td>
              <td>
                <span className="row-match">
                  <FileText size={12} />
                  {tag.excelRows?.length
                    ? `${tag.excelRows.length > 1 ? "Rows" : "Row"} ${tag.excelRows.map((row, index) => `${tag.excelSheets?.[index] ? `${tag.excelSheets[index]} ` : ""}#${row}`).join(", ")}`
                    : "Not in Excel"}
                </span>
              </td>
              <td>
                <span className={`status-badge ${tag.status}`}>
                  {tag.status === "matched" ? (
                    <Check size={11} />
                  ) : tag.status === "missing" ? (
                    <X size={11} />
                  ) : (
                    <TriangleAlert size={11} />
                  )}{" "}
                  {statusLabels[tag.status]}
                </span>
              </td>
              <td>
                <Button
                  variant="ghost"
                  size="sm"
                  className={`table-action ${tag.status}`}
                  onClick={() => {
                    if (tag.status === "pending") openQueue();
                    else {
                      setSelected(tag.equipment);
                      setBoxes(true);
                      if (tag.status === "missing") {
                        setLocatingTag(tag.tag);
                        setLocating(!sourcePdfUrl);
                        notify(`Select a region on the source drawing to locate ${tag.tag}.`);
                      }
                    }
                  }}
                >
                  {tag.status === "matched"
                    ? "View source"
                    : tag.status === "user-confirmed"
                      ? "User-confirmed"
                      : tag.status === "missing"
                        ? "Locate manually"
                        : tag.status === "ambiguous"
                          ? "Review source"
                          : "Resolve"}
                  <ArrowRight size={13} />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!filtered.length && (
        <div className="empty-state">
          <Search size={22} />
          <p>No matching tags</p>
        </div>
      )}
    </div>
  );

  return (
    <div className="untangle-app">
      {processing && (
        <div className="processing-overlay" role="status" aria-live="polite">
          <div className="processing-card">
            <Loader2 className="spin" size={28} />
            <h2>Processing P&ID</h2>
            <p>Extracting tags, building the process graph, and running integrity checks…</p>
          </div>
        </div>
      )}

      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Network size={25} />
          </div>
          <div>
            <div className="brand-name">
              UNTANGLE<span className="brand-point">.</span>
            </div>
            <div className="brand-subtitle">P&ID DIGITISATION PLATFORM</div>
          </div>
        </div>
        <div className="product-badge">
          Emerson P&ID Digitizer <span>v1.0</span>
        </div>
        <div className="topbar-right">
          <span className="system-pill">
            <span className={`status-dot ${liveConnected ? "matched" : "pending"}`} />
            {liveConnected ? "Backend connected" : "Demo data · upload to connect"}
          </span>
          <span className="header-divider" />
          <div className="emerson-wordmark">
            EMERSON<span>Automation Solutions</span>
          </div>
          {authUser ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" className="profile-trigger" aria-label="Open profile menu">
                  <span className="avatar">{initialsForName(authUser.fullName)}</span>
                  <span className="profile-trigger-copy">
                    <strong>{authUser.fullName}</strong>
                    <small>{authUser.role}</small>
                  </span>
                  <ChevronDown size={13} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="profile-menu" align="end">
                <DropdownMenuLabel className="profile-menu-heading">
                  <strong>{authUser.fullName}</strong>
                  <small>{authUser.email}</small>
                  <span>{authUser.role}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="profile-logout" onSelect={handleLogout}>
                  <LogOut size={14} />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setAuthReady(true)}>
              Sign in
            </Button>
          )}
        </div>
      </header>

      <main className="workspace">
        <div className="breadcrumb">
          <span>Workspace</span>
          <ChevronRight size={12} />
          <span>Project Alpha</span>
          <ChevronRight size={12} />
          <span className="breadcrumb-active">Sheet 01</span>
          <span className="session-label">
            {liveConnected ? "LIVE WORKSPACE" : "DEMO WORKSPACE"}
          </span>
        </div>

        <FileUploadDropzone
          processing={processing}
          onProcess={handleProcess}
          onPdfSelected={setSourcePdf}
          locked={!authUser}
          onRequestLogin={() => setAuthReady(true)}
          pdfName={projectName}
          excelName={excelName}
        />

        <section className="project-heading">
          <div className="project-info">
            <div className="project-icon">
              <FileText size={22} />
            </div>
            <div className="min-w-0">
              <div className="heading-eyebrow">PROJECT UNTANGLE</div>
              <h1>{projectName}</h1>
              <div className="project-meta">
                <span>Engineering drawing</span>
                <span className="meta-dot">·</span>
                <span>
                  {pdfPageCount} page{pdfPageCount === 1 ? "" : "s"}
                </span>
                <span className="meta-dot">·</span>
                <span className="processed">
                  <CheckCircle2 size={12} />
                  Processed in {workspaceMetrics.seconds}s
                </span>
              </div>
            </div>
          </div>
          <div className="project-actions">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" disabled={!authUser || savedRuns.length === 0}>
                  <FileText size={15} />
                  Saved runs ({savedRuns.length})
                  <ChevronDown size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>Recent saved runs</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {savedRuns.map((run) => (
                  <DropdownMenuItem
                    key={run.run_id}
                    disabled={processing || restoringRun}
                    onSelect={() => void openSavedRun(run.run_id)}
                  >
                    {run.pdf_filename}
                    {run.run_id === currentRunId ? " · Open" : ""}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button variant="outline" className="queue-button" onClick={openQueue}>
              <TriangleAlert size={15} />
              Clarification queue
              <span className="queue-count">
                {queue.length}
                <span className="pending-word"> pending</span>
              </span>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button disabled={exporting} className="export-button">
                  <Download size={15} />
                  {exporting ? "Exporting…" : "Export diagram"}
                  <ChevronDown size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {(["SVG", "PNG", "PDF"] as const).map((format) => (
                  <DropdownMenuItem
                    key={format}
                    onSelect={() => handleExport(format)}
                    disabled={view === "audit"}
                  >
                    <ArrowDownToLine size={14} />
                    Export as {format}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </section>

        <section className="metric-grid" aria-label="Project metrics">
          <div className="metric-card">
            <div className="metric-label">
              <span>Total I/O tags parsed</span>
              <Crosshair size={16} />
            </div>
            <div className="metric-value">
              {workspaceMetrics.matched}
              <span className="metric-denominator">/ {workspaceMetrics.total}</span>
              <span className="metric-qualifier success-text">Matched</span>
            </div>
            <div className="metric-progress">
              <span style={{ width: `${Math.min(100, Number(completeness))}%` }} />
            </div>
            <div className="metric-foot">
              <span>
                <span className="status-dot matched" />
                {completeness}% completeness
              </span>
              <span className="warning-text">{missingCount + pendingCount} require attention</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">
              <span>Major equipment retained</span>
              <Box size={16} />
            </div>
            <div className="metric-value">
              {workspaceMetrics.retained}
              <span className="metric-denominator">/ {workspaceMetrics.equipmentTotal}</span>
              <span className="metric-qualifier">Retained</span>
              <span className="metric-check">
                <CheckCircle2 size={17} />
              </span>
            </div>
            <div className="equipment-breakdown">
              <span>
                <b>{graphNodes.filter((n) => n.kind === "tank").length}</b> Tanks
              </span>
              <span>
                <b>{graphNodes.filter((n) => n.kind === "pump").length}</b> Pumps
              </span>
              <span>
                <b>{graphNodes.filter((n) => n.kind === "mixer").length}</b> Mixers
              </span>
              <span>
                <b>{graphNodes.filter((n) => n.kind === "exchanger").length}</b> Heat exchangers
              </span>
            </div>
            <div className="metric-foot">
              <span>All critical equipment preserved</span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">
              <span>Graph topology integrity</span>
              <ShieldCheck size={16} />
            </div>
            <div className="metric-value">
              {workspaceMetrics.integrity ?? "—"}
              {workspaceMetrics.integrity !== null && (
                <span className="metric-denominator percent">%</span>
              )}
              <span className="metric-qualifier">
                {workspaceMetrics.integrity === null ? "Not verified" : "Reported"}
              </span>
            </div>
            <div className="metric-foot">
              <span>
                <span
                  className={`status-dot ${workspaceMetrics.integrity === null ? "pending" : "matched"}`}
                />
                {workspaceMetrics.graphIntegrityLabel}
              </span>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">
              <span>Processing time</span>
              <Timer size={16} />
            </div>
            <div className="metric-value">
              {workspaceMetrics.seconds}
              <span className="metric-qualifier">Seconds</span>
              <span className="speed-badge">
                <Zap size={11} />
                Measured
              </span>
            </div>
            <div className="pipeline-label">
              PDF text <ChevronRight size={10} />
              Vector evidence
              <ChevronRight size={10} />
              Excel reconciliation
            </div>
            <div className="metric-foot">
              <span>
                <ShieldCheck size={11} />
                Local evidence pipeline
              </span>
              <span>Image-only OCR requires local Tesseract</span>
            </div>
          </div>
        </section>

        <div className="workspace-section-heading">
          <div>
            <Layers size={16} />
            <h2>Diagram workspace</h2>
            <span className="section-separator" />
            <span className="workspace-description">Source to simplified process</span>
          </div>
          <span className="trace-status">
            <Link2 size={13} />
            Bi-directional traceability active
            <span className="status-dot matched" />
          </span>
        </div>

        <section className={`diagram-workspace ${expanded ? `expanded-${expanded}` : ""}`}>
          <div className={`viewer source-viewer ${expanded === "source" ? "expanded-viewer" : ""}`}>
            <div className="viewer-heading">
              <div>
                <FileText size={15} />
                <h3>Source drawing viewer</h3>
              </div>
              <span className="viewer-label">ORIGINAL P&ID</span>
            </div>
            <div className="viewer-toolbar">
              <span className="page-label">
                Page <b>1</b> of {pdfPageCount}
                <ChevronDown size={12} />
              </span>
              <div className="zoom-controls">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Zoom out"
                  title="Zoom out"
                  onClick={() => setZoom((v) => Math.max(50, v - 25))}
                >
                  <Minus />
                </Button>
                <span className="mono">{zoom}%</span>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Zoom in"
                  title="Zoom in"
                  onClick={() => setZoom((v) => Math.min(200, v + 25))}
                >
                  <Plus />
                </Button>
                <span className="toolbar-divider" />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Reset zoom"
                  title="Reset zoom"
                  onClick={() => setZoom(100)}
                >
                  <RefreshCw />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Fit drawing"
                  title="Fit drawing"
                  onClick={() => setZoom(100)}
                >
                  <Maximize2 />
                </Button>
              </div>
              <label className="box-toggle">
                <span>Bounding boxes</span>
                <Switch aria-label="Bounding boxes" checked={boxes} onCheckedChange={setBoxes} />
              </label>
            </div>
            <div className="source-canvas">
              {sourcePdfUrl ? (
                <iframe
                  className="source-pdf-frame"
                  src={`${sourcePdfUrl}#page=1&toolbar=0&navpanes=0&view=Fit`}
                  title={`Uploaded source drawing: ${projectName}`}
                  style={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    border: 0,
                  }}
                />
              ) : (
                <SourceDiagram
                  selected={active}
                  onSelect={selectSource}
                  onHover={setHovered}
                  boxes={boxes}
                  zoom={zoom}
                  locating={locating}
                />
              )}
              <div className="canvas-scale">
                <span className="status-dot matched" />
                4K SOURCE
                <span className="canvas-scale-divider" />
                4096 × 3072
              </div>
              <Button
                variant="outline"
                size="icon"
                className="canvas-expand"
                aria-label="Expand source viewer"
                title="Expand source viewer"
                onClick={() => setExpanded(expanded === "source" ? null : "source")}
              >
                {expanded === "source" ? <X /> : <Maximize2 />}
              </Button>
              {locating && (
                <div className="locating-banner">
                  <Crosshair size={14} />
                  Locating tag
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Cancel locating"
                    onClick={() => {
                      setLocating(false);
                      setLocatingTag(null);
                    }}
                  >
                    <X />
                  </Button>
                </div>
              )}
              {locatingTag && sourcePdfUrl && (
                <div className="locating-banner" role="status">
                  After checking the uploaded PDF, confirm {locatingTag} manually.
                  <Button size="sm" onClick={() => confirmLocatedTag(locatingTag)}>
                    Confirm manually
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Cancel locating"
                    onClick={() => setLocatingTag(null)}
                  >
                    <X />
                  </Button>
                </div>
              )}
            </div>
            <div className="viewer-footer">
              <span>
                <span className="legend-square equipment-legend" />
                Equipment
                <span className="legend-square tag-legend" />
                I/O tags
              </span>
              <span>
                <Crosshair size={12} />
                {active
                  ? `${active} selected`
                  : `${matchedCount} detected regions · ${userConfirmedCount} user-confirmed`}
              </span>
            </div>
          </div>

          <div className="viewer-bridge">
            <ArrowLeftRight size={15} />
          </div>

          <div className={`viewer pfd-viewer ${expanded === "pfd" ? "expanded-viewer" : ""}`}>
            <div className="viewer-heading">
              <div>
                <GitBranch size={16} />
                <h3>Simplified process sketch</h3>
              </div>
              <span className="pfd-badge">PFD</span>
              <div className="pfd-zoom-controls" aria-label="PFD zoom controls">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Zoom PFD out"
                  title="Zoom out"
                  onClick={() => changePfdZoom(-1)}
                  disabled={pfdZoom !== "auto" && pfdZoom !== "fit" && pfdZoom <= 30}
                >
                  <Minus />
                </Button>
                <span>
                  {pfdZoom === "auto"
                    ? `${Math.round(pfdAutoScale * 100)}%`
                    : pfdZoom === "fit"
                      ? `${Math.round(pfdFitScale * 100)}%`
                      : `${pfdZoom}%`}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Zoom PFD in"
                  title="Zoom in"
                  onClick={() => changePfdZoom(1)}
                  disabled={pfdZoom !== "auto" && pfdZoom !== "fit" && pfdZoom >= 200}
                >
                  <Plus />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Fit PFD to view"
                  title="Fit to view"
                  onClick={() => setPfdZoom("fit")}
                >
                  Fit
                </Button>
              </div>
              <span
                className={`validated-badge ${workspaceMetrics.integrity === null ? "unverified-badge" : ""}`}
              >
                <ShieldCheck size={12} />
                {workspaceMetrics.integrity === null ? "Topology unverified" : "Integrity reported"}
              </span>
            </div>
            <div className="view-tabs" role="tablist" aria-label="Process view">
              <Button
                variant="ghost"
                role="tab"
                aria-selected={view === "pfd"}
                className={view === "pfd" ? "active-tab" : ""}
                onClick={() => setView("pfd")}
              >
                <Network size={13} />
                Simplified PFD
              </Button>
              <Button
                variant="ghost"
                role="tab"
                aria-selected={view === "topology"}
                className={view === "topology" ? "active-tab" : ""}
                onClick={() => setView("topology")}
              >
                <GitBranch size={13} />
                Full topology
              </Button>
              <Button
                variant="ghost"
                role="tab"
                aria-selected={view === "audit"}
                className={view === "audit" ? "active-tab" : ""}
                onClick={() => setView("audit")}
              >
                <Layers size={13} />
                Tag audit table
              </Button>
            </div>
            <div className="pfd-canvas">
              {view === "audit" ? (
                auditTable(true)
              ) : (
                <ProcessDiagram
                  selected={active}
                  onSelect={setSelected}
                  onHover={setHovered}
                  topology={view === "topology"}
                  nodes={graphNodes}
                  edges={graphEdges}
                  sourceTags={liveConnected ? tags : []}
                  zoom={pfdZoom}
                  onLayoutScaleChange={updatePfdScales}
                />
              )}
              <Button
                variant="outline"
                size="icon"
                className="canvas-expand"
                aria-label="Expand process viewer"
                title="Expand process viewer"
                onClick={() => setExpanded(expanded === "pfd" ? null : "pfd")}
              >
                {expanded === "pfd" ? <X /> : <Maximize2 />}
              </Button>
            </div>
            <div className="viewer-footer">
              <span>
                <span className="legend-line" />
                Process flow
                <span className="legend-square collapsed-legend" />
                Collapsed control loops
              </span>
              {(workspaceMetrics.rasterLineCandidates ?? 0) > 0 && (
                <span className="unverified-text">
                  <TriangleAlert size={12} />
                  {workspaceMetrics.rasterLineCandidates} raster stroke candidates ·{" "}
                  {workspaceMetrics.rasterIntersectionCandidates ?? 0} unresolved intersections ·
                  excluded from confirmed graph edges
                </span>
              )}
              <span
                className={workspaceMetrics.integrity === null ? "unverified-text" : "success-text"}
              >
                {workspaceMetrics.integrity === null ? (
                  <TriangleAlert size={12} />
                ) : (
                  <CheckCircle2 size={12} />
                )}
                {workspaceMetrics.integrity === null
                  ? "Edge validation unavailable"
                  : `${workspaceMetrics.changedEdges} edge changes reported`}
              </span>
            </div>
          </div>
        </section>

        <div className={`traceability-strip ${active ? "trace-active" : ""}`}>
          <Link2 size={14} />
          <span>
            {active ? (
              <>
                <b>{active}</b>
                <span className="trace-detail">
                  {" "}
                  linked across source drawing and process sketch
                </span>
              </>
            ) : (
              <>
                Source-linked equipment{" "}
                <span className="trace-detail">
                  · Exact tags. Preserved connections. Complete traceability.
                </span>
              </>
            )}
          </span>
          <span className="trace-strip-right">
            <ShieldCheck size={13} />
            Engineering integrity preserved
          </span>
        </div>

        <section className="audit-section">
          <div className="audit-heading">
            <Button
              variant="ghost"
              className="audit-collapse"
              onClick={() => setAuditOpen(!auditOpen)}
              aria-expanded={auditOpen}
            >
              <ShieldCheck size={17} />
              <h2>Tag check & completeness audit</h2>
              <span className="audit-record-count">
                {workspaceMetrics.total} unique inventory tags · {tags.length} audit rows
              </span>
              {auditOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </Button>
            <div className="audit-summary">
              <span>
                <span className="status-dot matched" />
                {matchedCount} matched
              </span>
              <span>
                <span className="status-dot missing" />
                {missingCount} missing
              </span>
              <span>
                <span className="status-dot pending" />
                {pendingCount} pending review
              </span>
              <span>{ambiguousCount} ambiguous</span>
              <span>{userConfirmedCount} user-confirmed</span>
              <span>
                {workspaceMetrics.inventoryRows ?? workspaceMetrics.total} Excel rows ·{" "}
                {workspaceMetrics.usableInventoryRows ?? workspaceMetrics.total} tagged
              </span>
              <span>
                {workspaceMetrics.detectedSourceTags ?? matchedCount} detected in PDF ·{" "}
                {workspaceMetrics.duplicateInventoryTags ?? 0} duplicate inventory tags
              </span>
              <span>{queue.length} clarification items</span>
              {(workspaceMetrics.deferredClarificationItems ?? 0) > 0 && (
                <span>
                  {workspaceMetrics.deferredClarificationItems} additional topology flags remain
                  provisional
                </span>
              )}
            </div>
          </div>
          {auditOpen && (
            <>
              <div className="audit-toolbar">
                <div className="audit-filters" role="tablist" aria-label="Tag status filter">
                  {[
                    { id: "all", label: "All tags", count: String(tags.length) },
                    { id: "matched", label: "Matched", count: String(matchedCount) },
                    { id: "missing", label: "Missing", count: String(missingCount) },
                    { id: "ambiguous", label: "Ambiguous", count: String(ambiguousCount) },
                    { id: "pending", label: "Pending review", count: String(pendingCount) },
                    {
                      id: "user-confirmed",
                      label: "User-confirmed",
                      count: String(userConfirmedCount),
                    },
                  ].map((f) => (
                    <Button
                      key={f.id}
                      role="tab"
                      aria-selected={filter === f.id}
                      variant="ghost"
                      size="sm"
                      className={filter === f.id ? "active-filter" : ""}
                      onClick={() => setFilter(f.id)}
                    >
                      {f.label}
                      <span>{f.count}</span>
                    </Button>
                  ))}
                </div>
                <div className="audit-search">
                  <Search size={14} />
                  <input
                    aria-label="Search tags"
                    placeholder="Search tags…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
              </div>
              {auditTable()}
              <div className="audit-bottom">
                <span>
                  Showing {filtered.length} records of {tags.length} tags
                </span>
                <span>
                  <FileText size={12} />
                  Reference: {excelName}
                  <span className="reference-badge">{liveConnected ? "LIVE" : "DEMO"}</span>
                </span>
              </div>
            </>
          )}
        </section>

        <footer className="workspace-footer">
          <span>
            <span className="status-dot matched" />
            Pipeline {liveConnected ? "live" : "demo"}
            <span className="footer-separator">/</span>
            <span>FastAPI + PyMuPDF + source geometry</span>
          </span>
          <span>
            <Zap size={12} />
            Local Tesseract OCR for image-only PDFs
            <span className="footer-separator">/</span>
            <span>UNTANGLE ENGINE v1.0</span>
            <CircleHelp size={14} />
          </span>
        </footer>
      </main>

      {notice && (
        <div className="notification" role="status">
          <CheckCircle2 size={17} />
          <span>{notice}</span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X />
          </Button>
        </div>
      )}

      <Dialog open={queueOpen} onOpenChange={setQueueOpen}>
        <DialogContent className="clarification-modal">
          <div className="modal-eyebrow">
            <TriangleAlert size={14} />
            PRE-RENDER CLARIFICATION
          </div>
          <DialogTitle>
            Ambiguity resolution queue{" "}
            <span className="muted-text">
              ({current ? queueIndex + 1 : 0} of {queue.length})
            </span>
          </DialogTitle>
          <DialogDescription>
            {current
              ? "Verify this connection before finalising the process graph."
              : "All intersections have been reviewed for this session."}
          </DialogDescription>
          {current ? (
            <>
              {current.evidenceCropDataUri ? (
                <figure className="clarification-source-evidence">
                  <img
                    src={current.evidenceCropDataUri}
                    alt={`Source PDF crop around process crossing on page ${(current.sourcePage ?? 0) + 1}`}
                  />
                  <figcaption>
                    Source PDF evidence · page {(current.sourcePage ?? 0) + 1}
                  </figcaption>
                </figure>
              ) : (
                <IntersectionCrop resolution={activeOption || resolution} />
              )}
              <div className="intersection-meta">
                <span className="mono">ITEM {current.id}</span>
                <span>
                  <Crosshair size={12} />
                  Near {current.near}
                </span>
              </div>
              <p className="clarification-question">{current.question}</p>
              <fieldset className="resolution-options">
                <legend className="sr-only">Intersection resolution</legend>
                {current.options.map((option) => {
                  const value: Resolution = /unresolved|flagged|not sure/i.test(option)
                    ? "unresolved"
                    : /junction|tee/i.test(option) &&
                        !/non-connecting|crossover|bridge/i.test(option)
                      ? "junction"
                      : "bridge";
                  const isSelected = activeOption === option;
                  return (
                    <label key={option} className={isSelected ? "selected-option" : ""}>
                      <input
                        type="radio"
                        name="resolution"
                        value={option}
                        checked={isSelected}
                        onChange={() => {
                          setSelectedOption(option);
                          setAnswerDrafts((drafts) => ({ ...drafts, [current.id]: option }));
                          setResolution(value);
                        }}
                      />
                      <div>
                        <span>{option}</span>
                        <small>
                          {option === current.defaultRecommendation
                            ? current.confidence != null
                              ? `Recommended · ${current.confidence}% confidence`
                              : "Review source evidence before applying"
                            : value === "unresolved"
                              ? "Retain in the clarification queue"
                              : "Apply to graph topology"}
                        </small>
                      </div>
                      {option === current.defaultRecommendation && (
                        <span className="recommended-icon">
                          <Zap size={14} />
                        </span>
                      )}
                    </label>
                  );
                })}
              </fieldset>
              <div className="modal-footer">
                <Button
                  variant="ghost"
                  onClick={() => {
                    const nextIndex = (queueIndex + 1) % queue.length;
                    setQueueIndex(nextIndex);
                    setResolution("bridge");
                    if (queue[nextIndex]) {
                      setSelectedOption(
                        answerDrafts[queue[nextIndex].id] ?? queue[nextIndex].selectedOption ?? "",
                      );
                    }
                  }}
                >
                  {queueIndex + 1 < queue.length ? "Skip / Next" : "Skip"}
                  <ChevronRight size={14} />
                </Button>
                <Button
                  onClick={() => void applyResolution()}
                  disabled={resolving || (liveConnected && Object.keys(answerDrafts).length === 0)}
                >
                  {resolving ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
                  {resolving
                    ? "Updating diagram…"
                    : liveConnected
                      ? `Confirm answers & update diagram (${Object.keys(answerDrafts).length})`
                      : "Apply & re-validate graph"}
                </Button>
              </div>
              <div className="modal-note">
                <ShieldCheck size={12} />
                Original source drawing remains unchanged
              </div>
            </>
          ) : (
            <div className="queue-empty">
              <CheckCircle2 size={40} />
              <h3>No clarification items remain.</h3>
              <p>
                Topology status:{" "}
                {workspaceMetrics.integrity === null ? "unverified" : "integrity reported"}.
              </p>
              <Button onClick={() => setQueueOpen(false)}>Return to workspace</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <AuthModal
        open={authReady && !authUser}
        onAuthenticated={(user, token) => {
          try {
            localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
            setAuthToken(token);
            setAuthUser(user);
          } catch {
            toast.error("Unable to save session", {
              description: "Browser storage is unavailable.",
            });
          }
        }}
      />
    </div>
  );
}
