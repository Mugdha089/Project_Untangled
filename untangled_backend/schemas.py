"""Pydantic request/response schemas for Project UNTANGLE."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


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
    status: TagStatus
    confidence: float = Field(..., ge=0.0, le=1.0)


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
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_page: Optional[int] = None
    source_bbox: Optional[List[int]] = Field(default=None, min_length=4, max_length=4)


class ClarificationItem(BaseModel):
    """Localized visual ambiguity awaiting pre-render clarification."""

    id: str
    location_label: str
    question: str
    crop_bbox: List[int] = Field(..., min_length=4, max_length=4)
    default_recommendation: str
    options: List[str]
    status: str


class KpiSummary(BaseModel):
    """Aggregate processing KPIs returned with every pipeline run."""

    total_tags: int
    matched_tags: int
    retained_equipment: int
    graph_integrity: str
    processing_time_seconds: float


class ProcessPidResponse(BaseModel):
    """Complete end-to-end pipeline payload for the frontend workspace."""

    kpis: KpiSummary
    nodes: List[EquipmentNode]
    edges: List[ProcessEdge]
    tag_audit: List[TagAuditItem]
    clarification_queue: List[ClarificationItem]
    pdf_page_count: int


class ResolveAmbiguityRequest(BaseModel):
    """Payload for resolving a clarification-queue item."""

    item_id: str
    selected_option: str


class ResolveAmbiguityResponse(BaseModel):
    """Updated KPIs and edges after an ambiguity resolution."""

    kpis: KpiSummary
    edges: List[ProcessEdge]
    resolved_item_id: str
    selected_option: str
    message: str


class HealthResponse(BaseModel):
    """Service health probe."""

    status: str
    model_status: str
    api_version: str
    service: Optional[str] = "UNTANGLE Backend"
