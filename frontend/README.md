# Diagram Digestive

The API client defaults to `http://localhost:8000`. To use a deployed backend,
copy `.env.example` to `.env` and set `VITE_UNTANGLE_API_BASE_URL` to its base
URL, then restart the frontend development server.

## Local development

From this directory, install dependencies and start the frontend:

```powershell
bun install
bun run dev
```

Run the backend separately from `untangled_backend`:

```powershell
cd ..\untangled_backend
Copy-Item .env.example .env
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Set the backend `UNTANGLE_CORS_ORIGINS` environment variable to the exact
frontend origin when using a non-local frontend host.

Act as a Principal UI/UX Designer and Senior Frontend Engineer specializing in industrial engineering software and CAD digitisation tools. 

Create a modern, high-impact, dark-themed interactive dashboard for "Project UNTANGLE" — an AI-Powered P&ID Digitisation & Process Simplification System.

### 1. Aesthetic, Vibe & Color Palette
- Aesthetic: Modern Industrial SaaS, Slate/Dark Navy, hyper-clean, executive control room vibe. Precision engineering look with crisp geometry, subtle borders, high visual contrast, and high readability.
- Dark Background Base: Slate Navy `#0F172A` (Tailwind `bg-slate-900`) and Deep Dark `#020617` (Tailwind `bg-slate-950`).
- Card/Panel Backgrounds: `#1E293B` (Tailwind `bg-slate-800/80` with `backdrop-blur-md` and `border-slate-700/50`).
- Brand Accents: 
  * Electric Teal `#0EA5E9` (Primary active accent, highlight borders, active tab indicators)
  * Cyan/Emerald `#14B8A6` (Success metrics, verified connections)
- Status Colors:
  * Green `#22C55E` (Matched Tags / 100% Graph Integrity)
  * Amber `#F59E0B` (Clarification Queue items / Low Confidence / Ambiguous)
  * Red `#EF4444` (Missing Tags / Broken Edge Warning)
- Typography: Inter or JetBrains Mono (for tag codes, metrics, bounding boxes).

### 2. Header & Top Navigation Bar
- Left: Logo "UNTANGLE" (Bold sans-serif with a stylized interconnected process-node icon in Electric Teal) + Subtitle pill badge: "Emerson P&ID Digitizer v1.0".
- Center: Active Project Indicator: "Project_Alpha_4K_Sheet_01.pdf" with status badge "Processed in 2.8s" (Green dot).
- Right Actions:
  * "Clarification Queue" Button with an Amber Badge count "3 Pending".
  * "Export Diagram" Dropdown Button (SVG, PNG, PDF).
  * System Performance Pill: "TensorRT Active | <3s/sheet".

### 3. Dashboard Grid Layout (Dual-Panel Interactive Workspace)
The main content area must be a split-screen dual-panel workspace with a top metric bar:

#### TOP KPI METRIC BAR (4 Compact Cards across top):
1. Total I/O Tags Parsed: "142 / 145 Matched" (Green progress bar, 97.9% completeness).
2. Major Equipment Retained: "12 / 12 Retained" (Tanks: 4, Pumps: 6, Heat Exchangers: 2).
3. Graph Topology Integrity: "100% Validated" (0 changed edges during layout).
4. Processing Time: "2.84 Seconds" (Spatial Tiling + YOLOv11 + PaddleOCR).

#### LEFT PANEL: "Original Source P&ID Blueprint (4K Raster Viewer)"
- Header: Title "Source Drawing Viewer", Page indicator "Page 1 of 1", Zoom controls (+, -, Reset, Fit), Bounding Box Toggle switch.
- Body: A dark mock high-res engineering PDF viewer showing line work with interactive bounding box overlays around symbols (e.g., Tank TK-101, Pump P-101A/B, Valve V-204) and highlighted text bounding boxes for tags (e.g., PT-101, FT-202).
- Feature: Clicking a highlighted region on this source image active-syncs with the right panel sketch.

#### RIGHT PANEL: "Generated Simplified Process Flow Diagram (D3.js Render)"
- Header: Title "Simplified Process Sketch (PFD)", View Toggles ("Simplified PFD View", "Full Topology Graph", "Tag Audit Table").
- Body: An ultra-clean, left-to-right horizontal flowchart diagram representing the simplified process path:
  * Tank TK-101 (Inlet) ──> Duty/Standby Pump Pair [P-101A / P-101B] ──> Heat Exchanger E-102 ──> Vessel V-102 (Outlet).
  * Smooth curved connector lines with glowing directional flow arrows (Teal).
  * Compact metadata pills attached to equipment showing collapsed control loop tags (e.g., `[PT-101 | FT-101 | LV-102]`).
  * Hovering/Clicking any node highlights its corresponding bounding box in the Left Source Panel with a glowing Teal link line animation ("Bi-directional Traceability").

### 4. Bottom Collapsible Panel: "Tag Check & Completeness Audit Report"
A clean tabular view displaying:
- Table Columns: Tag Name | Type | Source Bounding Box | Excel Row Match | Status | Action
- Sample Rows:
  * `PT-101` | Pressure Transmitter | [120, 240, 180, 310] | Row #14 | Matched (Green Badge) | View Source
  * `FT-202` | Flow Transmitter | [450, 110, 510, 160] | Row #22 | Matched (Green Badge) | View Source
  * `LT-309` | Level Transmitter | Not Detected | Row #88 | Missing in P&ID (Red Badge) | Locate Manually
  * `XV-104` | Solenoid Valve | Ambiguous Cross | Row #102 | Pending Review (Amber Badge) | Resolve

### 5. Interactive Modal: "Pre-Render Clarification Queue" (Triggerable / Floating Overlay)
- Header: "Ambiguity Resolution Queue (1 of 3)"
- Card Content:
  * Zoomed-in source crop showing two intersecting pipe lines with line highlight overlays.
  * Question: "At Pipe Intersection #04 (Near Pump P-101A), do these process lines form a connected junction or a crossing bridge?"
  * Radio Options: 
    [ ] Connected Junction (4-Way Tee)
    [x] Non-connecting Crossover Bridge (Default Recommendation - 92% Confidence)
    [ ] Unresolved / Keep Flagged
  * Action Buttons: "Apply & Re-validate Graph" (Primary Teal) and "Skip".

### 6. Code & Component Requirements
- Fully responsive layout utilizing Tailwind flex/grid.
- Use Lucide React icons (`FileText`, `CheckCircle2`, `AlertTriangle`, `Layers`, `Search`, `Download`, `Maximize2`, `RefreshCw`, `GitCommit`).
- Make the layout feel live, interactive, executive-ready, and polished for a top-tier hackathon demonstration.

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://diagram-digestive.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/458e1533-ac39-40d1-bc91-cfb1d175ab44).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
