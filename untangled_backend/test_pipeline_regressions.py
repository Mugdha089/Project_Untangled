"""Regression tests for live-upload sample isolation and evidence-based tags."""

from __future__ import annotations

import io
import unittest
from pathlib import Path

import httpx
import networkx as nx
from openpyxl import Workbook
from openpyxl import load_workbook

from excel_parser import load_excel_tags
from graph_engine import apply_ambiguity_resolution, build_process_graph
from main import _LAST_PIPELINE, app
from pdf_processor import PdfProcessError, match_excel_inventory, process_pdf

TEST_CASES = Path(__file__).resolve().parents[2] / "test_cases"
EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
DEMO_EQUIPMENT_TAGS = {"TK-101", "P-101A", "P-101B", "E-102", "V-102"}


def _fixture_files(case_name: str) -> tuple[Path, Path]:
    pdf_path = TEST_CASES / f"{case_name}.pdf"
    excel_path = TEST_CASES / f"{case_name}_io.xlsx"
    return pdf_path, excel_path


def _workbook_bytes(rows: list[tuple[str, str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Tag", "Type"])
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class PdfEvidenceTests(unittest.TestCase):
    def test_matching_requires_valid_source_coordinates(self) -> None:
        inventory = [
            {"tag_name": "PT-101", "type": "Pressure", "excel_row": 2},
            {"tag_name": "PT-102", "type": "Pressure", "excel_row": 3},
            {"tag_name": "PT-103", "type": "Pressure", "excel_row": 4},
        ]
        detections = [
            {"tag_name": "PT-101", "source_bbox": [10, 20, 30, 40]},
            {"tag_name": "PT-102", "source_bbox": [0, 0, 0, 0]},
            {"tag_name": "PT-103", "source_bbox": [30, 40, 10, 20]},
        ]

        audit = match_excel_inventory(detections, inventory)

        self.assertEqual(
            [(row["tag_name"], row["status"]) for row in audit],
            [
                ("PT-101", "Matched"),
                ("PT-102", "Missing in P&ID"),
                ("PT-103", "Missing in P&ID"),
            ],
        )

    def test_demo_entities_are_available_only_when_explicitly_requested(self) -> None:
        pdf_path, _ = _fixture_files("02_parallel_pumps")
        inventory = load_excel_tags(
            _fixture_files("02_parallel_pumps")[1].read_bytes()
        )["tags"]

        live_result = process_pdf(pdf_path.read_bytes(), excel_tags=inventory)
        demo_result = process_pdf(pdf_path.read_bytes(), demo_mode=True)

        live_tags = {item["tag"] for item in live_result["equipment"]}
        self.assertTrue(DEMO_EQUIPMENT_TAGS.isdisjoint(live_tags), live_tags)
        self.assertIn("TK-101", {item["tag"] for item in demo_result["equipment"]})

    def test_fixture_equipment_detection_uses_pdf_tags_and_symbols(self) -> None:
        for case_name in (
            "01_easy_linear",
            "02_parallel_pumps",
            "03_branch_merge",
            "04_control_utility",
            "05_dense_recycle",
            "07_missing_ambiguous_tags",
        ):
            with self.subTest(case=case_name):
                pdf_path, excel_path = _fixture_files(case_name)
                result = process_pdf(pdf_path.read_bytes(), filename=pdf_path.name)
                workbook = load_workbook(
                    excel_path, data_only=True, read_only=True
                )
                sheet = workbook["Major Equipment"]
                rows = list(sheet.values)
                header = [str(value) for value in rows[0]]
                tag_column = header.index("Equipment Tag")
                expected_column = header.index("Expected in PDF")
                expected = {
                    str(row[tag_column]).strip()
                    for row in rows[1:]
                    if str(row[expected_column]).strip().lower() == "yes"
                }
                actual = {item["tag"] for item in result["equipment"]}
                self.assertEqual(actual, expected)
                workbook.close()

    def test_scanned_fixture_remains_explicitly_unsupported(self) -> None:
        pdf_path, _ = _fixture_files("06_scanned_image_only")
        with self.assertRaisesRegex(PdfProcessError, "OCR is not configured"):
            process_pdf(pdf_path.read_bytes(), filename=pdf_path.name)


class PipelineRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def _process_case(self, case_name: str) -> httpx.Response:
        pdf_path, excel_path = _fixture_files(case_name)
        return await self.client.post(
            "/api/process-pid",
            files={
                "file_pdf": (
                    pdf_path.name,
                    pdf_path.read_bytes(),
                    "application/pdf",
                ),
                "file_excel": (
                    excel_path.name,
                    excel_path.read_bytes(),
                    EXCEL_CONTENT_TYPE,
                ),
            },
        )

    async def test_uploaded_pdf_does_not_receive_demo_equipment(self) -> None:
        response = await self._process_case("02_parallel_pumps")

        self.assertEqual(response.status_code, 200, response.text)
        node_tags = {node["tag"] for node in response.json()["nodes"]}
        self.assertTrue(node_tags)
        self.assertTrue(
            DEMO_EQUIPMENT_TAGS.isdisjoint(node_tags),
            node_tags,
        )

    async def test_scanned_pdf_reports_ocr_unavailability_without_fabricated_matches(
        self,
    ) -> None:
        response = await self._process_case("06_scanned_image_only")

        self.assertEqual(response.status_code, 400, response.text)
        detail = response.json()["detail"].lower()
        self.assertIn("no extractable text", detail)
        self.assertIn("ocr", detail)

    async def test_case_07_keeps_deliberately_absent_instrument_tags_missing(
        self,
    ) -> None:
        response = await self._process_case("07_missing_ambiguous_tags")

        self.assertEqual(response.status_code, 200, response.text)
        rows = {row["tag_name"]: row for row in response.json()["tag_audit"]}
        self.assertEqual(rows["FT-601"]["status"], "Matched")
        self.assertEqual(rows["TT-601"]["status"], "Matched")
        for tag in ("LT-609", "FT-601A", "PT-699"):
            self.assertEqual(rows[tag]["status"], "Missing in P&ID")
            self.assertEqual(rows[tag]["source_bbox"], [0, 0, 0, 0])

    async def test_excel_only_tag_is_not_reported_as_detected(self) -> None:
        pdf_path, _ = _fixture_files("01_easy_linear")
        response = await self.client.post(
            "/api/process-pid",
            files={
                "file_pdf": (
                    pdf_path.name,
                    pdf_path.read_bytes(),
                    "application/pdf",
                ),
                "file_excel": (
                    "tags.xlsx",
                    _workbook_bytes(
                        [("PT-101", "Pressure"), ("PT-999", "Pressure")]
                    ),
                    EXCEL_CONTENT_TYPE,
                ),
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        rows = {row["tag_name"]: row for row in response.json()["tag_audit"]}
        self.assertEqual(rows["PT-101"]["status"], "Matched")
        self.assertGreater(
            rows["PT-101"]["source_bbox"][2],
            rows["PT-101"]["source_bbox"][0],
        )
        self.assertEqual(rows["PT-999"]["status"], "Missing in P&ID")
        self.assertEqual(rows["PT-999"]["source_bbox"], [0, 0, 0, 0])

    async def test_invalid_excel_does_not_substitute_demo_inventory(self) -> None:
        pdf_path, _ = _fixture_files("01_easy_linear")
        response = await self.client.post(
            "/api/process-pid",
            files={
                "file_pdf": (
                    pdf_path.name,
                    pdf_path.read_bytes(),
                    "application/pdf",
                ),
                "file_excel": (
                    "invalid.xlsx",
                    b"not an Excel workbook",
                    EXCEL_CONTENT_TYPE,
                ),
            },
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Unable to parse Excel inventory", response.json()["detail"])

    async def test_ambiguity_endpoint_does_not_create_fallback_demo_edges(self) -> None:
        previous = _LAST_PIPELINE.copy()
        _LAST_PIPELINE.clear()
        _LAST_PIPELINE.update(
            {
                "edges": [],
                "kpis": None,
                "clarification_ids": set(),
                "total_tags": 0,
                "matched_tags": 0,
                "retained_equipment": 0,
            }
        )
        try:
            response = await self.client.post(
                "/api/resolve-ambiguity",
                json={"item_id": "amb_04", "selected_option": "junction"},
            )
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIn("Process a PDF", response.json()["detail"])
        finally:
            _LAST_PIPELINE.clear()
            _LAST_PIPELINE.update(previous)

    async def test_unresolved_clarification_remains_available_for_later_resolution(self) -> None:
        response = await self._process_case("05_dense_recycle")
        self.assertEqual(response.status_code, 200, response.text)
        original_edge_ids = {edge["id"] for edge in response.json()["edges"]}

        unresolved = await self.client.post(
            "/api/resolve-ambiguity",
            json={"item_id": "amb_04", "selected_option": "Unresolved / Keep Flagged"},
        )
        self.assertEqual(unresolved.status_code, 200, unresolved.text)
        self.assertEqual(
            {edge["id"] for edge in unresolved.json()["edges"]}, original_edge_ids
        )
        self.assertIn("Partially verified", unresolved.json()["kpis"]["graph_integrity"])
        self.assertNotIn("100%", unresolved.json()["kpis"]["graph_integrity"])

        resolved = await self.client.post(
            "/api/resolve-ambiguity",
            json={
                "item_id": "amb_04",
                "selected_option": "Connected Junction (4-Way Tee)",
            },
        )
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(
            {edge["id"] for edge in resolved.json()["edges"]}, original_edge_ids
        )

        duplicate = await self.client.post(
            "/api/resolve-ambiguity",
            json={
                "item_id": "amb_04",
                "selected_option": "Connected Junction (4-Way Tee)",
            },
        )
        self.assertEqual(duplicate.status_code, 404, duplicate.text)

    async def test_all_fixture_pairs_return_evidence_based_results(self) -> None:
        for case_name in (
            "01_easy_linear",
            "02_parallel_pumps",
            "03_branch_merge",
            "04_control_utility",
            "05_dense_recycle",
            "06_scanned_image_only",
            "07_missing_ambiguous_tags",
        ):
            with self.subTest(case=case_name):
                response = await self._process_case(case_name)
                if case_name == "06_scanned_image_only":
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertIn("OCR", response.json()["detail"])
                    continue

                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertNotIn("100%", payload["kpis"]["graph_integrity"])
                equipment_tags = {
                    node["tag"]
                    for node in payload["nodes"]
                    if node["type"] != "junction"
                }
                _, excel_path = _fixture_files(case_name)
                workbook = load_workbook(
                    excel_path, data_only=True, read_only=True
                )
                equipment_rows = list(workbook["Major Equipment"].values)
                headers = [str(value) for value in equipment_rows[0]]
                tag_column = headers.index("Equipment Tag")
                expected_column = headers.index("Expected in PDF")
                expected_tags = {
                    str(row[tag_column]).strip()
                    for row in equipment_rows[1:]
                    if str(row[expected_column]).strip().lower() == "yes"
                }
                self.assertEqual(equipment_tags, expected_tags)
                for node in payload["nodes"]:
                    self.assertEqual(node["source_page"], 0)
                    self.assertEqual(len(node["source_bbox"]), 4)
                    if node["type"] != "junction":
                        x1, y1, x2, y2 = node["source_bbox"]
                        self.assertGreater(x2, x1)
                        self.assertGreater(y2, y1)
                self.assertTrue(
                    all(edge["relation"] == "process_pipe" for edge in payload["edges"])
                )
                workbook.close()

        response = await self.client.post(
            "/api/resolve-ambiguity",
            json={"item_id": "amb_04", "selected_option": "Unresolved / Keep Flagged"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("100%", response.json()["kpis"]["graph_integrity"])
        self.assertIn("topology retained", response.json()["kpis"]["graph_integrity"])


class SourceTopologyTests(unittest.TestCase):
    def _fixture_result(self, case_name: str) -> tuple[dict, dict]:
        pdf_path, excel_path = _fixture_files(case_name)
        pdf_result = process_pdf(pdf_path.read_bytes(), filename=pdf_path.name)
        workbook = load_workbook(excel_path, data_only=True, read_only=True)
        rows = list(workbook["Instrument Tag List"].values)
        headers = [str(value) for value in rows[0]]
        tag_column = headers.index("Tag Number")
        type_column = headers.index("Instrument Type")
        inventory = [
            {
                "tag_name": str(row[tag_column]).strip(),
                "type": str(row[type_column] or "Instrument"),
                "excel_row": index + 1,
            }
            for index, row in enumerate(rows[1:], start=1)
            if row[tag_column]
        ]
        audit = match_excel_inventory(pdf_result["tags"], inventory)
        result = build_process_graph(
            pdf_result["equipment"], audit, pdf_result["drawing_evidence"]
        )
        workbook.close()
        return pdf_result, result

    def test_all_native_fixture_connections_are_supported_by_source_paths(self) -> None:
        for case_name in (
            "01_easy_linear",
            "02_parallel_pumps",
            "03_branch_merge",
            "04_control_utility",
            "05_dense_recycle",
            "07_missing_ambiguous_tags",
        ):
            with self.subTest(case=case_name):
                pdf_path, excel_path = _fixture_files(case_name)
                pdf_result = process_pdf(pdf_path.read_bytes(), filename=pdf_path.name)
                workbook = load_workbook(excel_path, data_only=True, read_only=True)
                tag_rows = list(workbook["Instrument Tag List"].values)
                tag_headers = [str(value) for value in tag_rows[0]]
                tag_column = tag_headers.index("Tag Number")
                type_column = tag_headers.index("Instrument Type")
                inventory = [
                    {
                        "tag_name": str(row[tag_column]).strip(),
                        "type": str(row[type_column] or "Instrument"),
                        "excel_row": index + 1,
                    }
                    for index, row in enumerate(tag_rows[1:], start=1)
                    if row[tag_column]
                ]
                graph = build_process_graph(
                    pdf_result["equipment"],
                    match_excel_inventory(pdf_result["tags"], inventory),
                    pdf_result["drawing_evidence"],
                )
                workbook_connections = list(
                    workbook["Expected Connections"].values
                )
                headers = [str(value) for value in workbook_connections[0]]
                from_column = headers.index("From")
                to_column = headers.index("To")
                relationship_column = headers.index("Relationship")
                expected = [
                    row
                    for row in workbook_connections[1:]
                    if str(row[relationship_column]).lower()
                    not in {"utility", "instrument-signal"}
                ]
                for connection in expected:
                    source = str(connection[from_column]).strip()
                    target = str(connection[to_column]).strip()
                    self.assertTrue(
                        nx.has_path(graph["nx_graph"], source, target),
                        f"{case_name}: no source-supported route {source} -> {target}",
                    )
                self.assertTrue(
                    all(edge["relation"] == "process_pipe" for edge in graph["edges"])
                )
                self.assertTrue(
                    all(edge["flow_direction"] == "undirected" for edge in graph["edges"])
                )
                self.assertNotIn("100%", graph["graph_integrity"])
                workbook.close()

    def test_parallel_pumps_branches_and_merges_remain_distinct(self) -> None:
        _, graph = self._fixture_result("02_parallel_pumps")
        tags = {node["tag"] for node in graph["nodes"]}
        self.assertTrue({"P-201A", "P-201B"}.issubset(tags))
        self.assertGreaterEqual(
            sum(node["type"] == "junction" for node in graph["nodes"]), 2
        )
        self.assertTrue(
            any(node["tag"] == "P-201A" for node in graph["nodes"])
        )

    def test_branch_merge_and_recycle_loops_are_retained(self) -> None:
        _, branch_graph = self._fixture_result("03_branch_merge")
        self.assertGreaterEqual(
            sum(node["type"] == "junction" for node in branch_graph["nodes"]), 2
        )
        _, recycle_graph = self._fixture_result("05_dense_recycle")
        self.assertTrue(nx.cycle_basis(recycle_graph["nx_graph"]))
        recycle_junctions = {
            node["tag"]
            for node in recycle_graph["nodes"]
            if node["type"] == "junction"
            and recycle_graph["nx_graph"].has_edge("V-501", node["tag"])
            and recycle_graph["nx_graph"].has_edge(node["tag"], "FCV-501")
        }
        self.assertTrue(recycle_junctions)

    def test_utility_and_instrument_signal_strokes_are_not_process_edges(self) -> None:
        pdf_result, graph = self._fixture_result("04_control_utility")
        kinds = {segment["kind"] for segment in pdf_result["drawing_evidence"]["segments"]}
        self.assertTrue({"process", "utility", "instrument_signal"}.issubset(kinds))
        self.assertTrue(all(edge["relation"] == "process_pipe" for edge in graph["edges"]))

    def test_ordering_without_pipe_geometry_cannot_create_edges(self) -> None:
        equipment = [
            {
                "tag": "TK-1",
                "type": "tank",
                "source_bbox": [0, 0, 10, 10],
            },
            {
                "tag": "V-1",
                "type": "vessel",
                "source_bbox": [100, 0, 110, 10],
            },
        ]
        result = build_process_graph(equipment, [], None)
        self.assertEqual(result["edges"], [])
        self.assertIn("Unverified", result["graph_integrity"])

    def test_duplicate_equipment_and_self_edges_are_rejected(self) -> None:
        pdf_path, _ = _fixture_files("01_easy_linear")
        pdf_result = process_pdf(pdf_path.read_bytes(), filename=pdf_path.name)
        equipment = pdf_result["equipment"] + [dict(pdf_result["equipment"][0])]
        result = build_process_graph(
            equipment, [], pdf_result["drawing_evidence"]
        )
        tags = [node["tag"] for node in result["nodes"]]
        self.assertEqual(len(tags), len(set(tags)))
        self.assertTrue(all(edge["source"] != edge["target"] for edge in result["edges"]))

    def test_unmarked_crossing_does_not_join_process_paths(self) -> None:
        equipment = [
            {"tag": "P-1", "type": "pump", "source_page": 0, "source_bbox": [8, 38, 12, 42], "source_symbol_bbox": [5, 35, 15, 45]},
            {"tag": "V-1", "type": "vessel", "source_page": 0, "source_bbox": [88, 38, 92, 42], "source_symbol_bbox": [85, 35, 95, 45]},
            {"tag": "E-1", "type": "exchanger", "source_page": 0, "source_bbox": [48, 8, 52, 12], "source_symbol_bbox": [45, 5, 55, 15]},
            {"tag": "TK-2", "type": "tank", "source_page": 0, "source_bbox": [48, 88, 52, 92], "source_symbol_bbox": [45, 85, 55, 95]},
        ]
        evidence = {
            "classified_process_lines": 2,
            "segments": [
                {"page": 0, "start": [0, 40], "end": [100, 40], "kind": "process"},
                {"page": 0, "start": [50, 0], "end": [50, 100], "kind": "process"},
            ],
        }
        result = build_process_graph(equipment, [], evidence)
        self.assertFalse(nx.has_path(result["nx_graph"], "P-1", "E-1"))
        self.assertFalse(any(node["type"] == "junction" for node in result["nodes"]))

    def test_clarification_does_not_claim_graph_validation(self) -> None:
        edge = {
            "id": "edge_a_b",
            "source": "A",
            "target": "B",
            "flow_direction": "undirected",
            "relation": "process_pipe",
            "confidence": 0.85,
        }
        result = apply_ambiguity_resolution(
            [edge],
            item_id="amb_04",
            selected_option="Connected Junction",
            retained_equipment=2,
            total_tags=1,
            matched_tags=1,
        )
        self.assertEqual(result["edges"], [edge])
        self.assertNotIn("100%", result["kpis"]["graph_integrity"])


if __name__ == "__main__":
    unittest.main()
