"""Pydantic request/response schemas for Project UNTANGLE."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=100)


class AuthUser(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    user: AuthUser


TagStatus = Literal["Matched", "Missing in P&ID", "Pending Review", "Ambiguous"]
EquipmentType = Literal[
    "tank",
    "pump",
    "mixer",
    "exchanger",
    "vessel",
    "valve",
    "filter",
    "junction",
]


class TagAuditItem(BaseModel):
    """Single I/O tag audit row linking Excel inventory to P&ID evidence."""

    tag_name: str
    type: str
    source_bbox: List[int] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box [x1, y1, x2, y2]",
    )
    source_page: Optional[int] = None
    excel_row: int
    excel_rows: List[int] = Field(default_factory=list)
    excel_sheet: Optional[str] = None
    excel_sheets: List[Optional[str]] = Field(default_factory=list)
    status: TagStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_text: Optional[str] = None
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    reason: Optional[str] = None


class EquipmentNode(BaseModel):
    """Primary equipment retained in the simplified PFD graph."""

    id: str
    tag: str
    type: EquipmentType
    label: str
    source_bbox: List[int] = Field(..., min_length=4, max_length=4)
    source_page: int = 0
    source_symbol_bbox: Optional[List[int]] = Field(
        default=None,
        min_length=4,
        max_length=4,
    )
    collapsed_tags: List[str] = Field(default_factory=list)
    duty_standby: bool = False


class ProcessEdge(BaseModel):
    """Source-supported process connection, directed only when evidence exists."""

    id: str
    source: str
    target: str
    flow_direction: str
    relation: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_status: str = "source_geometry"
    source_segment_ids: List[str] = Field(default_factory=list)
    source_page: Optional[int] = None
    source_bbox: Optional[List[int]] = Field(default=None, min_length=4, max_length=4)


class RasterLineCandidate(BaseModel):
    """Raster stroke geometry retained as provisional, unclassified evidence."""

    id: str
    page: int
    start: List[float] = Field(..., min_length=2, max_length=2)
    end: List[float] = Field(..., min_length=2, max_length=2)
    source_bbox: List[int] = Field(..., min_length=4, max_length=4)
    orientation: Literal["horizontal", "vertical"]
    kind: Literal["unclassified"] = "unclassified"
    evidence_status: Literal["provisional"] = "provisional"


class RasterIntersectionCandidate(BaseModel):
    """Raster lines intersect geometrically; connectivity remains unresolved."""

    id: str
    page: int
    point: List[float] = Field(..., min_length=2, max_length=2)
    source_bbox: List[int] = Field(..., min_length=4, max_length=4)
    segment_ids: List[str] = Field(default_factory=list)
    evidence_status: Literal["unresolved"] = "unresolved"


class ClarificationItem(BaseModel):
    """Localized visual ambiguity awaiting pre-render clarification."""

    id: str
    location_label: str
    question: str
    crop_bbox: List[int] = Field(..., min_length=4, max_length=4)
    source_page: int = 0
    evidence_crop_data_uri: Optional[str] = None
    default_recommendation: str
    options: List[str]
    status: str
    selected_option: Optional[str] = None


class ClarificationDecision(BaseModel):
    """Persisted user choice for one run's clarification item."""

    item_id: str
    selected_option: str
    status: str
    updated_at: str


class KpiSummary(BaseModel):
    """Counts for Excel rows, unique tags, source detections, audit statuses and clarification items."""

    total_tags: int
    matched_tags: int
    retained_equipment: int
    graph_integrity: str
    processing_time_seconds: float
    inventory_rows: int = 0
    usable_inventory_rows: int = 0
    unique_inventory_tags: int = 0
    duplicate_inventory_tags: int = 0
    duplicate_inventory_rows: int = 0
    detected_source_tags: int = 0
    missing_tags: int = 0
    ambiguous_tags: int = 0
    pdf_only_tags: int = 0
    pending_review_tags: int = 0
    audit_rows: int = 0
    clarification_items: int = 0
    deferred_clarification_items: int = 0
    raster_line_candidates: int = 0
    raster_intersection_candidates: int = 0


class ProcessPidResponse(BaseModel):
    """Complete end-to-end pipeline payload for the frontend workspace."""

    run_id: str
    created_at: str
    kpis: KpiSummary
    nodes: List[EquipmentNode]
    edges: List[ProcessEdge]
    tag_audit: List[TagAuditItem]
    clarification_queue: List[ClarificationItem]
    raster_line_candidates: List[RasterLineCandidate] = Field(default_factory=list)
    raster_intersection_candidates: List[RasterIntersectionCandidate] = Field(
        default_factory=list
    )
    pdf_page_count: int
    pdf_filename: str
    excel_filename: str
    clarification_decisions: List[ClarificationDecision] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Concise metadata for a saved processing run."""

    run_id: str
    created_at: str
    pdf_filename: str
    excel_filename: str
    kpis: KpiSummary


class RunListResponse(BaseModel):
    runs: List[RunSummary]


class ResolveAmbiguityRequest(BaseModel):
    """Payload for resolving a clarification-queue item."""

    run_id: str
    item_id: str
    selected_option: str


class ClarificationAnswer(BaseModel):
    item_id: str = Field(..., min_length=1)
    selected_option: str = Field(..., min_length=1)


class ResolveAmbiguitiesRequest(BaseModel):
    run_id: str = Field(..., min_length=1)
    answers: List[ClarificationAnswer] = Field(..., min_length=1)


class ResolveAmbiguityResponse(BaseModel):
    """Updated graph and KPIs after a clarification decision."""

    run_id: str
    kpis: KpiSummary
    nodes: List[EquipmentNode] = Field(default_factory=list)
    edges: List[ProcessEdge]
    resolved_item_id: str
    selected_option: str
    message: str
    topology_changed: bool = False


class HealthResponse(BaseModel):
    """Service health probe."""

    status: str
    model_status: str
    api_version: str
    service: Optional[str] = "UNTANGLE Backend"
