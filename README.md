# Project UNTANGLE

## Research, product strategy, architecture, MVP roadmap, and team execution guide

**Working title:** UNTANGLE --- Evidence-Driven P&ID Simplification\
**Tagline:** *From complex engineering drawing to a clear process
sketch---with every tag and connection accounted for.*\
**Track:** VIT Code_Apex 3.0 --- Emerson, Project UNTANGLE\
**Document purpose:** A beginner-friendly but technically grounded guide
for planning the PPT, MVP, prototype, and a longer-term research-grade
solution.

> **Important:** This document separates (1) requirements explicitly
> stated in the official challenge brief, (2) our proposed design, and
> (3) research observations from published sources. Performance figures
> are targets to test, not claims of achieved performance. This is a
> planning document, not a guarantee of hackathon shortlisting,
> patentability, or industrial safety.

------------------------------------------------------------------------

# 1. Executive summary

Project UNTANGLE asks us to build a tool that takes two inputs:

1.  A customer P&ID as a PDF.
2.  An I/O list as an Excel spreadsheet.

It must automatically create a simplified process sketch that keeps the
major equipment and every instrument tag listed in the Excel file,
preserves the correct process connections and flow direction, and makes
the drawing easier to read. It must also report which I/O-list tags were
found and which were not found on the source P&ID.

A P&ID is a technical drawing of a plant process. It shows equipment
such as tanks, vessels, pumps and heat exchangers, plus pipes, valves
and instruments that measure or control the process.

**The central difficulty is not drawing a neat picture. It is preserving
the process logic while simplifying the picture.** If a generated sketch
looks polished but connects the wrong pump or sends flow in the wrong
direction, it fails the challenge.

## Recommended solution direction

Build a **graph-first, evidence-linked simplification pipeline**:

1.  Read and render the PDF.
2.  Extract text/tags and detect likely equipment and lines.
3.  Match extracted tags against the supplied Excel I/O list.
4.  Convert detected equipment and connections into a structured process
    graph.
5.  Check the graph for uncertain, missing or inconsistent information.
6.  Recognise simple patterns such as duty/standby pumps where the
    evidence supports them.
7.  Automatically lay out the graph left-to-right with fewer bends and
    crossovers.
8.  Generate a simplified sketch and a tag-check report.
9.  Let a user inspect uncertain links against the source drawing;
    corrections should be recorded and re-run through the pipeline
    rather than manually redrawing the output.

For the hackathon MVP, use the supplied sample drawings and focus on a
narrow but complete path. Do not try to train a large custom vision
model from scratch on day one.

## Recommended differentiator

**Evidence-linked, topology-preserving simplification with selective human verification.**

Every output object is strictly traceable to evidence in the source: a tag, a detected symbol, a line segment, a matched Excel row, or a clearly marked inference. The system flags uncertain connections instead of silently inventing them. The output includes a compact validation panel showing tag coverage, unmatched tags, major equipment retained, and connection checks. For localized ambiguities that remain important and cannot be resolved automatically, UNTANGLE provides a pre-render clarification queue that presents high-resolution source crops with targeted multi-choice questions (e.g. crossing vs. tee junction, nozzle attachment), updating the underlying NetworkX graph deterministically.

### Sourced Literature Findings & Industrial Digitisation Practices

Established research in P&ID digitization documents clear technical trade-offs:
1. **Multi-Stage Decomposition (Mani et al., 2020; Microsoft ISE):** Industrial pipelines separate symbol detection (YOLO/Faster-R-CNN), text detection/OCR, and linework tracing (morphological thinning, Hough transforms, vectorization). Monolithic end-to-end models struggle with the extreme density and heterogeneous scales of engineering diagrams.
2. **Line Discontinuity & Intersections (Paliwal et al., 2021; Kang et al., 2022):** Classical line-tracing algorithms consistently break when process pipes pass behind equipment symbols or text callouts, leading to fragmented graphs. Conversely, heuristic gap-closing often joins unrelated parallel lines.
3. **Silent Graph Hallucinations (Stürmer et al., 2024; Multimodal LLMs):** Unconstrained neural approaches frequently hallucinate connections across disconnected lines or fail to preserve crucial recycle loops, making them unsafe for process engineering without strict geometric validation.

### Actual Limitations in Real Plant Datasets (Emerson Track 1 Findings)

1. **Scanned Raster PDFs:** Industrial drawings such as the official `Sample P&IDs_Sanitized 1.pdf` (4 pages, 1067×748 px) contain zero extractable text or vector linework. Direct text extractors fail; high-accuracy OCR and raster vectorization are strictly required.
2. **DCS Software Records vs. Physical Drawings:** In the official Track 1 inventory (`UNTANGLE_03_Filtered_IO_Records 1.xlsx`), 172 out of 271 records are DCS software-derived tags (Location: DCS, I/O Type: SW, Signal Type: `-`, internal alarms and logic blocks). These do not and should not appear as standalone physical piping symbols on P&IDs. Classifying them as "Missing in P&ID" is an engineering defect; UNTANGLE classifies them as "Pending Review" with explicit source notes.
3. **Planar Line Crossing Ambiguities:** Without explicit 3D elevation or bridge/jump-arc symbols, planar 4-way crossings cannot be safely disambiguated by geometry alone. UNTANGLE surfaces these as localized visual clarification items with source crops rather than guessing flow paths.
4. **Nozzle Attachment Gaps:** Linework frequently stops 2–10 pt short of equipment boundaries. UNTANGLE distinguishes verified connections from provisional nozzle alignments and requires user confirmation for ambiguous nozzles.

This is a credible, defensible engineering solution that preserves the integrity of safety-critical process flows rather than presenting an unverified cosmetic sketch.

------------------------------------------------------------------------

# 2. The official problem statement, in simple language

The organiser's brief says that customer P&IDs contain process lines
with many bends, turns and crossovers. Operators need a simplified
control-room view of the same process. The simplified view should retain
only major equipment and the instruments listed in the I/O list,
connected in the correct flow sequence. Engineers currently mark up
drawings, trace flow and redraw them by hand, which is slow, repetitive
and prone to errors.

The challenge is to build an AI-based tool that accepts a customer P&ID
PDF and its I/O list and automatically generates a simplified sketch.

## 2.1 What each phrase means

  -----------------------------------------------------------------------
  Official requirement /  Plain-language meaning  What our software must
  phrase                                          do
  ----------------------- ----------------------- -----------------------
  Customer P&ID (PDF)     The original            Accept a PDF and render
                          engineering drawing     its pages clearly for
                          supplied by the         processing
                          customer                

  I/O list (Excel)        A spreadsheet listing   Read the spreadsheet,
                          important               identify the tag
                          instruments/tags        column, and validate
                                                  its rows

  Read the P&ID           Understand what is      Find equipment, labels,
                          shown in the drawing    instruments and pipe
                                                  paths

  Keep I/O-list tags      Do not lose the         Ensure each listed tag
                          instruments the         is placed in the output
                          customer says are       or explicitly reported
                          important               as unresolved

  Keep major equipment    Preserve tanks,         Detect and retain major
                          vessels, pumps,         equipment in the
                          exchangers and similar  simplified drawing
                          main items              

  Trace the flow path     Understand which pieces Build and validate a
                          of equipment are        connection graph from
                          connected and in what   the pipe paths
                          order                   

  Redraw as a simplified  Generate a cleaner      Create a new diagram
  sketch                  drawing automatically   from structured data;
                                                  no manual redrawing

  Correct flow sequence   The process order must  Preserve
                          remain the same         source-supported edges
                                                  and flow direction

  Straight, easy-to-read  The output should be    Use a layout algorithm
  lines                   easier to follow than   to reduce bends and
                          the source              crossings without
                                                  changing connectivity

  Duty/standby pumps      Two pumps may serve     Detect this pattern
                          parallel or backup      only when labels, tags,
                          roles                   source structure or
                                                  explicit rules support
                                                  it

  Tag-check report        Compare the Excel list  Report found, missing,
                          with the source drawing ambiguous and duplicate
                                                  tags

  Generic                 It should not work only Test on a sample or
                          on one memorised sample layout not used to
                                                  hard-code the result

  Transparency            Tell the organiser      Document libraries,
                          which external tools    APIs, model names and
                          and models are used     what each does
  -----------------------------------------------------------------------

## 2.2 Common instrument tag examples

The supplied brief gives examples such as:

-   **PT** --- pressure transmitter.
-   **FT** --- flow transmitter.
-   **LT** --- level transmitter.
-   **TT** --- temperature transmitter.
-   **FV / LV** --- flow valve / level valve in the brief's simplified
    tag legend.
-   **M** --- pump motor.
-   **T / V / P / E** --- tank / vessel / pump / exchanger in the
    brief's equipment legend.

These are useful examples, not a complete universal symbol standard. Tag
conventions vary between projects. Our code should preserve the
customer's exact tag text and should not infer an equipment type from a
prefix unless that mapping is configured and validated.

## 2.3 What the final output must contain

The official brief states that output may be PDF, PPT or image and must
show:

1.  All I/O-list tags and all major equipment.
2.  The same connections and flow direction as the source P&ID.
3.  Readable, simplified left-to-right flow, with minimal bends and no
    unnecessary crossovers.
4.  A tag-check report showing I/O-list tags found versus not found on
    the P&ID.
5.  A working demo on the provided sample P&IDs, source code, and a
    short note explaining the approach.

The brief also says the tool must create the sketch itself; manual
redrawing is not allowed. Sample P&IDs and I/O lists are for hackathon
use only and must not be shared. Any third-party tools, APIs and AI
models must be declared.

**Consequently, the first acceptance test should be: upload source PDF +
Excel → click Generate → obtain sketch + tag report + validation summary
without manually drawing the output.**

------------------------------------------------------------------------

# 3. What makes the task technically difficult?

A P&ID combines several different kinds of information on one page:

-   Text: equipment IDs, instrument tags, line numbers and notes.
-   Symbols: pumps, tanks, valves, transmitters and other components.
-   Lines: process pipes, signal lines and connectors.
-   Relationships: which line touches which component, which tags belong
    to which symbols, and which direction the process flows.
-   Layout: where the objects sit on the page.

The computer must understand both **what each object is** and **how the
objects connect**.

### Example of a failure

Suppose the source contains Tank A → Pump A/B (duty/standby) → Heat
Exchanger → Tank B. The output may look neat, but if the algorithm
accidentally connects both pumps in series rather than showing them as
parallel alternatives, it has changed the process meaning.

### The main failure modes to anticipate

1.  Small or blurry tag text is read incorrectly.
2.  A tag is read but matched to the wrong symbol.
3.  A pipe crossing is mistaken for a connection---or a real junction is
    missed.
4.  A pipe runs behind a symbol and is incorrectly broken.
5.  A line is mistaken for a signal line or annotation.
6.  An arrow or flow direction is not detected.
7.  A tag in Excel is missing from the source or is too blurry to find.
8.  A layout optimiser changes visual routing in a way that makes the
    process ambiguous.
9.  Duty/standby or parallel equipment is guessed from a superficial
    pattern.
10. The pipeline succeeds on the supplied sample but fails on a
    different drawing style.

Our architecture must explicitly address these failures rather than
relying on one large prompt to a vision model.

------------------------------------------------------------------------

# 4. Existing solutions and research review

## 4.1 What existing research already does

The following published work shows that P&ID digitisation is an
established research and engineering area. It is important not to claim
that simply "using AI to read a P&ID" is novel.

### A. Automatic Information Extraction from P&IDs (2019)

Paper: https://arxiv.org/abs/1901.11383

This work studies extraction of equipment/symbols, pipelines and textual
information from P&IDs, then associates these elements to form a
structured representation. It highlights difficulties caused by
different image resolutions, noisy text, visually similar symbols and
complicated pipeline junctions.

**Lesson for us:** Tag extraction alone is insufficient. The
relationships between lines, symbols and text matter.

### B. Automatic Digitization of Engineering Diagrams Using Deep Learning and Graph Search (CVPR Workshops, 2020)

Paper: https://doi.org/10.1109/CVPRW50498.2020.00096

The pipeline combines computer vision to detect symbols and associate
text with graph search to find connections. It shows that a graph
representation can support downstream applications such as
equipment-to-sensor mapping.

**Lesson for us:** A graph-based internal representation is a sound
engineering choice, but graph reconstruction itself is not a new
invention.

### C. Digitize-PID (2021 preprint)

Paper: https://arxiv.org/abs/2109.03794

This work describes a pipeline for detecting, understanding and
reconciling symbols, lines and text, including validation using domain
knowledge. It also reports a synthetic dataset and explains the
challenges of complex, noisy diagrams.

**Lesson for us:** Use more than one stage. Detecting an object,
understanding its role, and reconciling conflicting evidence should be
separate operations.

### D. End-to-end digitisation of image-format P&IDs (Journal of Computational Design and Engineering, 2022)

Article: https://academic.oup.com/jcde/article/9/4/1298/6611631

The work combines recognition of symbols, text and lines with connection
reconstruction and generation of a digital P&ID. Its reported
experiments also illustrate that processing real engineering drawings
can be computationally expensive.

**Lesson for us:** Accuracy and end-to-end reliability matter more than
merely producing a picture. The sample set and evaluation method must be
described honestly.

### E. PID2Graph / transformer-based graph extraction (2024 preprint)

Paper: https://arxiv.org/abs/2411.13929

This work explores extracting graph structure from P&IDs with a model
that learns objects and relationships, and compares it with a modular
approach. It is relevant because it focuses on the relationships between
diagram elements rather than only detecting individual symbols.

**Lesson for us:** The graph is a central representation of the process,
not just an intermediate file.

### F. Recent hybrid methods

A 2026 article describes combining deep learning and rules for
line-object recognition in dense P&IDs:
https://www.sciencedirect.com/science/article/abs/pii/S0098135426000244

A 2026 preprint explores a multimodal language-model pipeline that
separates visual extraction from topology reasoning:
https://arxiv.org/abs/2607.19568

**Lesson for us:** Hybrid approaches---vision for observations,
rules/graphs for structural reasoning---are an active direction. A
generic claim that "we combine AI and rules" is not enough to establish
novelty.

### G. Commercial engineering software

Industrial engineering software suites also support intelligent P&ID
design, data management, or digitisation. For example, Hexagon's Smart
P&ID product information is available at:
https://hexagon.com/products/smart-p-id

AVEVA's engineering and design product information is available at:
https://www.aveva.com/en/products/engineering/

These are broad product pages, not proof that each product performs the
exact hackathon conversion workflow. Commercial products may operate on
structured/native engineering data, use specialised configuration, or
target different lifecycle workflows. We must verify feature-by-feature
before claiming a gap.

## 4.2 What gaps are relevant to this exact challenge?

The research above shows that symbol recognition, OCR, line detection
and graph reconstruction already exist. We should therefore focus on the
*specific end-to-end outcome* demanded by the organiser.

  ---------------------------------------------------------------------------------------
  Challenge-relevant   Why it matters    Proposed response  How we will test it
  gap or risk                            in UNTANGLE        
  -------------------- ----------------- ------------------ -----------------------------
  Correct tags may be  Every I/O-list    Treat the Excel    Count tags in input list
  lost during          instrument must   list as an         versus output graph; explain
  simplification       appear            explicit           every mismatch
                                         completeness       
                                         constraint         

  Extracted text may   A tag can appear  Match using text,  Manually check a labelled
  be matched to the    but be attached   spatial proximity, subset and calculate
  wrong instrument     to the wrong      symbol evidence    tag-association precision
                       object            and tag            
                                         conventions;       
                                         retain confidence  

  Correct-looking      Process topology  Build an explicit  Compare source-supported
  lines may represent  is the most       graph and validate connections with generated
  wrong connections    important         its edges before   graph
                       semantic property drawing            

  Ambiguous            Pipe crossovers   Detect candidate   Include
  intersections can    and junctions are junctions and mark crossing-without-connection
  cause false          visually similar  low-confidence     and true-junction examples
  connections                            cases for review   

  Generic methods may  The brief         Separate reusable  Hold back one drawing/layout
  fail on unseen       explicitly        algorithms from    during development and test
  layouts              expects           sample-specific    it at the end
                       generalisation    configuration      

  Simplification may   Layout must not   Freeze the         Verify that layout changes
  make the diagram     alter process     validated graph    only coordinates, not graph
  readable but change  logic             before applying    edges
  its meaning                            visual layout      

  AI may invent        LLMs can produce  Use structured     Create deliberate
  missing information  plausible but     outputs, source    missing/ambiguous cases and
                       unsupported       evidence and       check that the tool flags
                       answers           deterministic      them
                                         checks; never      
                                         silently invent    
                                         edges              

  Users need to trust  Industrial        Add                Select an output component
  the output           diagrams are      source-to-output   and show its source evidence
                       technical         traceability and   
                       artefacts         an audit report    

  The organiser        It is an explicit Build it as a      Test found, missing,
  requires a tag-check deliverable       first-class        duplicate and ambiguous tags
  report                                 report, not an     
                                         afterthought       

  Sample-only success  The brief expects Use the supplied   Report performance separately
  is not enough        the tool to work  samples for        for development and held-out
                       on a P&ID it has  development, then  sample
                       never seen        hold out at least  
                                         one sample if      
                                         permitted          
  ---------------------------------------------------------------------------------------

**Research caution:** These are challenge-specific risks and design
opportunities inferred from the brief and literature, not proof that no
existing product addresses them. We must not call any row a confirmed
industry-wide research gap until we compare exact existing product
capabilities and papers more thoroughly.

------------------------------------------------------------------------

# 5. Our proposed product: UNTANGLE Evidence-Driven Simplifier

## 5.1 Core promise

"Upload a P&ID and its I/O list. UNTANGLE automatically creates a
cleaner process sketch, checks tag coverage, preserves the validated
process graph, and shows evidence for uncertain or unmatched elements."

The product should never promise "perfectly understands every industrial
diagram" before we have measured it. Use an automation-first,
confidence-aware workflow: process high-confidence elements automatically;
for important localized ambiguities, ask a basic clarification question
before final rendering; disclose anything that remains unresolved. The
user is not expected to validate every component or manually reconstruct
the drawing.

## 5.2 Main user journey

1.  The user opens the UNTANGLE workspace.
2.  Uploads a P&ID PDF.
3.  Uploads the corresponding I/O-list Excel file.
4.  The system validates the files and identifies likely tag columns.
5.  The user sees a processing status and a source preview.
6.  The system extracts tags, symbols and line candidates.
7.  It builds a structured graph and performs checks.
8.  It generates a simplified sketch automatically.
9.  The user sees the sketch alongside a validation panel.
10. The pipeline creates a tag report listing matched, not-found,
    duplicate and ambiguous tags. The report is generated automatically
    from the PDF detections and Excel inventory.
11. Before final rendering, the system presents a compact **Clarification
    Queue** only for localized, material ambiguities that automated checks
    cannot resolve reliably (for example, whether two lines connect or
    merely cross). Each item includes a zoomed source crop, a short plain-
    language question, and simple options such as Yes/No or a small
    multiple-choice set.
12. The user answers the easy questions at a glance. The system applies
    each answer to that specific candidate connection or detection, records
    the decision and reruns graph-integrity checks. Questions already
    resolved automatically are not shown.
13. The user can select an output object to see its source region and
    extracted evidence, then export the sketch and reports.

The user must not be asked to manually redraw the diagram or perform the
pipeline's core jobs. In particular, do not ask the user to locate every
Excel-listed component in the PDF, decide whether each tag exists, or
manually identify all connections. Those are automated pipeline and
checklist responsibilities. The clarification queue is only for simple,
localized questions about a specific unresolved visual ambiguity. If the
user cannot answer, keep that item explicitly unresolved and disclose its
impact in the quality report rather than forcing a guess.

------------------------------------------------------------------------

# 6. Unique selling proposition (USP)

## Recommended USP: "Evidence-linked, constraint-checked simplification"

Many tools can make a diagram visually neat. Our proposal is to make the
simplification **auditable**: the generated sketch should carry a
structured record of where its objects and connections came from, and
the system should verify the organiser's explicit completeness and
topology requirements before declaring the output ready.

### What makes this useful?

-   **Tag completeness:** The I/O spreadsheet is treated as a checklist.
    A tag is not silently dropped.
-   **Connection preservation:** The system validates a graph before
    rendering it.
-   **Evidence traceability:** Selecting an output item reveals its
    source location, tag text, and connection evidence.
-   **Selective interactive ambiguity resolution:** Before final rendering,
    the pipeline asks only short, localized questions about material
    ambiguities it cannot resolve reliably. Each question shows a cropped
    view of the relevant source area and uses simple Yes/No or basic
    multiple-choice options. Examples include "Do these two lines connect
    or just cross?" or choosing between two plausible readings of a short
    tag. The user should be able to answer at a glance without needing to
    interpret the entire P&ID or understand the software's algorithms.
-   **Automation-first boundary:** The pipeline itself detects components,
    extracts and reconciles tags against the Excel I/O list, reconstructs
    connections, and produces the tag checklist. It must not ask users to
    find every component from Excel in the drawing or perform these core
    tasks manually. A tag that was not detected is reported as "not found
    in the drawing"; it is not automatically treated as proof that the
    physical component is absent.
-   **Uncertainty disclosure:** If a material ambiguity cannot be resolved
    automatically and the user cannot answer, mark it unresolved and
    explain its possible impact. Never silently convert a guess into a
    verified connection.
-   **Automated quality report:** The tool explains what passed, what
    failed, what was clarified by the user, and what remains uncertain.
-   **Layout separated from logic:** The visual layout engine can move
    objects around without altering the validated graph.
-   **Repeatable testing:** The same inputs and configuration can be
    processed again, and results can be compared.

### What we should not claim

Do not claim: - "First AI system to digitise P&IDs." - "Zero errors"
before comprehensive testing. - "Patentable" or "patent-pending" without
legal review and a filed application. - "Works on every P&ID" based only
on the organiser's samples. - "Novel because it uses a vision-language
model, OCR, a graph, or an LLM." These are existing techniques.

A stronger, defensible claim is: "We are developing a tag-constrained,
evidence-linked simplification pipeline and will evaluate its tag
coverage, graph fidelity, uncertainty handling and readability on the
challenge samples and held-out examples."

------------------------------------------------------------------------

# 7. MVP features: what to build first

The MVP must be a small but complete working product. A beautiful
frontend without automatic generation will not satisfy the problem
statement.

## Priority 0 --- essential for a valid MVP

### Feature 1: PDF and Excel upload

-   Accept PDF and `.xlsx` inputs.
-   Validate file type, size and whether the files can be opened.
-   Show clear error messages.
-   Preview the source PDF and the I/O-list rows.

### Feature 2: I/O-list parsing

-   Read the Excel workbook using `pandas` / `openpyxl`.
-   Allow selection or auto-detection of the tag column.
-   Normalise spaces and case for matching while preserving the original
    tag.
-   Identify empty rows and duplicate tags.
-   Do not silently remove questionable rows.

### Feature 3: Source PDF processing

-   Render PDF pages at a suitable resolution.
-   Use embedded PDF text where available.
-   Use OCR for scanned/image-based pages.
-   Save the source page and bounding box for each extracted item.

### Feature 4: Equipment, tag and line extraction

-   Detect common major equipment and instrument tags.
-   Detect likely pipe paths and candidate junctions.
-   Record the location and confidence of each detection.
-   Start with the organiser's sample drawing styles; design modules so
    additional layouts can be added later.

### Feature 5: Structured graph

Represent the process in data rather than drawing directly from raw
image pixels.

Example conceptual objects: - Nodes: tank, pump, exchanger, instrument,
valve. - Edges: pipe connection, instrument association, flow direction
where known. - Attributes: tag, equipment type, source page, source
bounding box, confidence, evidence.

Keep the types of relationships distinct. A pipe connection is not the
same as an instrument's association with equipment.

### Feature 6: Validation and tag report

Report: - I/O tags found in the source. - I/O tags not found. - Tags
found but matched ambiguously. - Duplicate tags. - Major equipment
detected and retained. - Connections with insufficient evidence. -
Validation status and warnings.

### Feature 7: Automatic simplified drawing

-   Generate from the structured graph, not from a manually drawn
    picture.
-   Use a left-to-right flow layout where supported.
-   Reduce line bends and crossings.
-   Show every required I/O tag and major equipment item.
-   Preserve the graph connections after layout.
-   Export SVG or PNG first; add PDF export if time permits.

### Feature 8: End-to-end demonstration

A single button or workflow should process the two input files and
return: 1. Simplified sketch. 2. Tag-check report. 3. Validation
summary. 4. Downloadable outputs.

## Priority 1 --- high-value differentiators if the core works

### A. Click-to-source traceability

Click an output component or tag and show the corresponding source-page
crop and extracted text. This directly demonstrates evidence rather than
merely claiming that the AI is correct.

### B. Selective interactive ambiguity resolution (before final rendering)

Create a compact **Clarification Queue** after automated extraction and
initial graph checks but before final rendering. Include only ambiguities
that are (a) material to process topology, tag interpretation, or flow
representation, (b) still unresolved after the pipeline's own checks, and
(c) expressible as a simple question a user can answer by looking at a
small crop of the source drawing.

For each item, show: (1) a zoomed crop with the relevant lines/symbols
highlighted, (2) a plain-language question, (3) two or a few plausible
answers, and (4) an option such as "Not sure / leave unresolved." Example:
"At this crossing, do the pipes connect? — Yes, they connect / No, they
just cross / Not sure." Other suitable examples include confirming one
of two plausible OCR readings or choosing between two detected flow-arrow
directions when the crop makes the distinction understandable.

Batch the questions into one review screen rather than interrupting the
user one at a time. Do not ask the user to find an Excel-listed component,
confirm every tag, identify all equipment, trace the entire process, or
construct the graph. Those are pipeline responsibilities and belong in
the automated tag checklist and quality report. Do not ask questions whose
answers would not affect the output. Apply each answer only to the specific
item shown, record the decision and source location, then rerun graph
integrity and consistency checks before rendering. If the user selects
"Not sure," retain and disclose the unresolved state rather than guessing.

This feature is intended to reduce avoidable user effort, not guarantee
that complex drawings need no review. Track the number of questions,
answer time, unresolved rate, and errors remaining to test whether the
workflow actually improves usability and accuracy.

### C. Duty/standby pattern handling

Detect a pattern such as P-101A / P-101B only when supported by labels,
tags, source topology or explicit configuration. Render the two pumps as
parallel alternatives when the evidence supports that interpretation.

### D. Graph-integrity check

Compare the validated graph with the graph used for rendering. Assert
that the layout step has not changed the node or edge set.

### E. Reproducible run summary

Save input file hashes or run identifiers, processing settings,
library/model versions and validation results. Avoid storing
confidential customer files beyond what is needed.

## Priority 2 --- after the hackathon MVP

-   Multi-page P&ID support and cross-page connector resolution.
-   More symbol families and customer-specific tag conventions.
-   Configurable equipment dictionaries and symbol libraries.
-   Revision comparison between two P&ID versions.
-   More advanced review history and versioned corrections (the basic pre-render clarification queue is part of the proposed MVP).
-   More robust graph reconstruction for complex crossovers and dense
    lines.
-   Additional output formats.
-   Enterprise authentication, project workspaces and controlled data
    retention.
-   Integration with engineering data formats such as DEXPI where
    available and appropriate.

Do not build these before the end-to-end MVP works.

------------------------------------------------------------------------

# 8. Technical architecture: recommended approach

## 8.1 Architecture overview

``` text
                  USER
                   |
        +----------+-----------+
        |                      |
   P&ID PDF                I/O List Excel
        |                      |
        v                      v
  PDF page renderer      Excel parser + validator
        |                      |
        v                      v
  Text extraction/OCR     Normalised tag inventory
  Symbol detection        Duplicate/empty-row checks
  Pipe/line detection            |
        |                        |
        +-----------+------------+
                    |
                    v
        Evidence and association layer
  (tag ↔ symbol, line ↔ component, confidence)
                    |
                    v
          Process graph builder
      (nodes, edges, attributes, direction)
                    |
                    v
       Graph and completeness validation
   (tag coverage, uncertain edges, topology checks)
                    |
                    v
       Automatic graph-layout / renderer
                    |
          +---------+---------+
          |                   |
          v                   v
   Simplified sketch      Tag/quality report
          |                   |
          +---------+---------+
                    |
                    v
       Traceability + downloadable results
```

**Design rule:** Vision and OCR provide observations; the graph stores
the process structure; validation checks the structure; the layout
engine draws it. Do not make the vision model responsible for every
stage in one unverified step.

## 8.2 Suggested technology stack

  -----------------------------------------------------------------------
  Layer                   Recommended choice      Why
  ----------------------- ----------------------- -----------------------
  Frontend                React + Vite +          Fast development,
                          TypeScript              reusable components and
                                                  a polished demo

  Styling                 Tailwind CSS            Rapid consistent UI
                                                  construction

  Backend API             Python + FastAPI        Beginner-friendly and
                                                  suitable for image/data
                                                  processing

  PDF rendering           PyMuPDF                 Render PDF pages and
                                                  access embedded text

  Image processing        OpenCV                  Thresholding, line
                                                  candidates, contours
                                                  and image clean-up

  OCR                     PaddleOCR or EasyOCR    Extract text from
                                                  scanned drawings;
                                                  benchmark both on
                                                  samples before
                                                  committing

  Tabular processing      pandas + openpyxl       Read Excel lists and
                                                  create reports

  Object detection        Start with OpenCV / a   Avoid starting with an
                          pretrained model;       expensive custom
                          fine-tune only if       training effort
                          labelled data and time  
                          justify it              

  Graph representation    NetworkX                Represent nodes, edges,
                                                  attributes and perform
                                                  graph checks

  Graph layout            Graphviz / `dot`, or a  Produce readable
                          tested graph-layout     left-to-right diagrams
                          library                 

  Output                  SVG first, then PNG/PDF SVG is clear and
                                                  supports clickable
                                                  objects; PNG/PDF are
                                                  easy to share

  Persistence             Local files / SQLite    Avoid adding database
                          for the MVP             complexity before the
                                                  pipeline works

  AI model                Optional vision-capable Use only where it adds
                          LLM API for ambiguous   measurable value;
                          extraction assistance   validate its outputs

  Tests                   pytest for backend, a   Prevent changes from
                          small fixed             silently breaking the
                          input/output regression graph or report
                          set                     

  Deployment              Local demo first; then  Do not let deployment
                          a Python-capable host   block core development
                          and frontend host if    
                          needed                  
  -----------------------------------------------------------------------

**API security:** Keep API keys in environment variables and out of
source control. Use only data permitted by the hackathon rules. The
organiser says sample drawings and lists are for hackathon use only and
must not be shared; do not upload them to an external service unless the
event rules explicitly permit that use.

## 8.3 Should we use an LLM for everything?

No. A vision-language model may help interpret a cropped region, suggest
a symbol label, or explain an ambiguous case. But it may hallucinate a
plausible connection. A safer pattern is:

1.  Ask the model for a structured candidate with evidence.
2.  Check that the referenced text, object and line detections actually
    exist.
3.  Apply deterministic validation rules.
4.  Mark unresolved conflicts as uncertain.
5.  Never treat fluent language as proof of a physical connection.

------------------------------------------------------------------------

# 9. The data model we should build

A minimal internal representation makes the rest of the system testable.

## 9.1 Example node

``` json
{
  "id": "equipment_001",
  "type": "pump",
  "tag": "P-101A",
  "source_page": 1,
  "bbox": [120, 240, 180, 310],
  "confidence": 0.94,
  "evidence": ["detected_symbol_21", "ocr_text_18"]
}
```

The numbers are illustrative only. They are not extracted from the
challenge sample.

## 9.2 Example edge

``` json
{
  "source": "tank_001",
  "target": "pump_001",
  "relation": "process_pipe",
  "flow_direction": "source_to_target",
  "confidence": 0.88,
  "evidence": ["line_segment_12", "junction_4"]
}
```

Again, this is a schema example, not a verified connection from a real
drawing.

## 9.3 Why keep evidence?

If a judge asks, "Why did your tool connect this tank to this pump?", we
should be able to show the line segments and detections that support the
connection. If the evidence is weak, the software should say so. This is
much stronger than saying "the AI predicted it."

------------------------------------------------------------------------

# 10. Implementation roadmap: exact order

The order matters. Do not let four people independently generate
disconnected parts and then attempt integration on the final day.

## Phase 0 --- first 60--90 minutes: inspect the inputs and agree on the contract

**Owner:** All four members, coordinated by Member 1.

1.  Open the official sample P&ID PDF and I/O Excel file locally.
2.  Identify whether the PDF has selectable text or is scanned.
3.  Inspect the Excel workbook, sheets, headers and tag column.
4.  List major equipment and I/O tags in one small sample.
5.  Agree on the first supported sample and the expected output format.
6.  Write a tiny JSON schema for nodes, edges, tags and evidence.
7.  Create the repository, environment and task board.
8.  Choose a single working branch/integration strategy.
9.  Record the external tools and models that may be used.

**Deliverable:** A sample input pair, a minimal schema and an agreed
definition of "done".

## Phase 1 --- first half-day: build a complete vertical slice

A vertical slice means the entire workflow works in a limited form.

1.  Build a simple frontend with two upload fields.
2.  Build the FastAPI endpoint that accepts the PDF and Excel.
3.  Parse the Excel and produce the tag inventory.
4.  Render the first PDF page to an image.
5.  For the first sample, extract tags using embedded text or OCR.
6.  Build a small structured graph from extracted/verified detections.
7.  Generate a basic SVG/PNG from that graph.
8.  Produce a tag report.
9.  Connect frontend and backend.
10. Run the workflow from upload to download.

At this point, the output may be limited to a small subset of symbols,
but it must be automatically generated. A narrow end-to-end pipeline is
better than a perfect frontend with no functioning core.

## Phase 2 --- second half-day: improve correctness and presentation

1.  Add detection for the next most important equipment/symbol type.
2.  Improve tag-to-symbol association.
3.  Add connection candidates and graph validation.
4.  Add left-to-right graph layout.
5.  Add the found/not-found/duplicate/ambiguous tag report.
6.  Add a source preview and evidence panel.
7.  Add a basic pre-render Clarification Queue for a small set of
    localized ambiguities, with cropped evidence and Yes/No or simple
    multiple-choice options; include a "Not sure" option.
8.  Apply answers to the corresponding graph items and rerun validation.
9.  Test known edge cases.
8.  Fix the highest-impact errors before adding optional features.

## Phase 3 --- next development session: broaden coverage

1.  Process more supplied samples.
2.  Separate code that is generic from sample-specific configuration.
3.  Add support for scanned and text-based PDFs if not already
    supported.
4.  Add more equipment and instrument classes.
5.  Improve pipe junction and crossover handling.
6.  Add explicit handling for parallel/duty-standby equipment where
    evidence is sufficient.
7.  Compare output graphs against manually checked reference graphs.
8.  Measure performance and document limitations.

## Phase 4 --- polish the prototype

1.  Make processing progress visible.
2.  Display clear error messages.
3.  Use consistent colours and typography.
4.  Ensure labels remain readable when exported.
5.  Add "download sketch" and "download report".
6.  Show validation counts, not just a green success badge.
7.  Add a demo mode using permitted sample data.
8.  Prepare a short recorded backup demo in case the live environment
    fails.

## Phase 5 --- final validation and pitch

1.  Freeze the code before final testing.
2.  Re-run the full test set from clean inputs.
3.  Verify every listed tag is either retained or explicitly reported.
4.  Verify that rendering does not alter graph edges.
5.  Confirm the exported files open correctly.
6.  Rehearse the demo with one person speaking and another operating it.
7.  Prepare a limitations slide and a roadmap.
8.  Credit the libraries, datasets and models used.

------------------------------------------------------------------------

# 11. Four-member team distribution

Give each person a clear deliverable and define the interfaces between
their work.

## Member 1 --- Technical lead and graph/validation owner

**Main responsibility:** The correctness of the process representation.

Tasks: - Define the node/edge schema with the team. - Implement graph
creation and connection validation. - Implement tag coverage and
graph-integrity checks. - Coordinate integration and code review. -
Maintain the test cases and acceptance checklist.

Deliverables: - `graph_builder.py` - `validator.py` - `tests/` - Schema
document and integration checklist

This member does not need to know all industrial instrumentation theory
at the start, but must understand the agreed schema and the limits of
the available evidence.

## Member 2 --- PDF, OCR and vision pipeline owner

**Main responsibility:** Turn the drawing into candidate objects and
evidence.

Tasks: - Render PDF pages. - Extract embedded text and run OCR when
needed. - Detect common symbols and line candidates. - Store bounding
boxes and confidence values. - Match tags to candidate symbols using
defined rules. - Produce a structured JSON output for the graph builder.

Deliverables: - `pdf_processor.py` - `ocr_extractor.py` -
`symbol_detector.py` (can begin as a narrow baseline) - Example
extraction JSON and notes on known errors

This is the highest-risk technical component. The member should
benchmark the tools against the actual sample before choosing a model.

## Member 3 --- Frontend and visualisation owner

**Main responsibility:** Make the solution understandable and polished.

Tasks: - Create the upload screen. - Display the source drawing and
parsed I/O list. - Show processing progress and errors. - Render the
simplified graph or SVG. - Add the tag report, validation summary and
evidence viewer. - Connect to backend APIs and ensure the UI does not
use fake success states.

Deliverables: - React frontend - Upload and result components - Diagram
preview and download controls - Responsive, consistent demo interface

## Member 4 --- Backend integration, output and demo owner

**Main responsibility:** Make the components work together end-to-end.

Tasks: - Set up FastAPI endpoints and file handling. - Connect PDF/OCR
output, Excel parsing, graph builder and renderer. - Generate SVG/PNG
and reports. - Add logging, error handling and run IDs. - Create
sample-run scripts and end-to-end tests. - Prepare demo steps and
presentation evidence.

Deliverables: - `main.py` / API routes - `report_generator.py` -
`layout_renderer.py` integration - End-to-end run script and demo
checklist

## Shared responsibilities

All four members should: - Use one shared schema. - Commit small changes
frequently. - Never overwrite each other's work without coordination. -
Run the same end-to-end test before claiming completion. - Review the
limitations and explain the pipeline in their own words. - Ensure all
AI-generated code is reviewed and understood.

### Integration rule

Before working in parallel, agree on the input and output of each
module. For example, the OCR module returns JSON detections; the graph
module consumes that JSON; the renderer consumes the validated graph. If
everyone uses a different format, integration will consume the hackathon
time.

------------------------------------------------------------------------

# 12. Testing and evaluation plan

A credible project needs more than screenshots. Use a small labelled
evaluation set and publish the method.

## 12.1 Build a reference set

For each permitted sample drawing, manually create a checked reference
containing: - I/O tags present in the drawing. - Major equipment
objects. - Correct equipment and pipe relationships. - Flow direction
wherever the source clearly indicates it. - Known ambiguities or
unreadable elements.

Do this carefully; the reference set is how we determine whether the
tool is right.

## 12.2 Metrics to measure

  -------------------------------------------------------------------------
  Metric                  What it measures          Why it matters
  ----------------------- ------------------------- -----------------------
  Tag detection recall    Fraction of required tags Missing an I/O-list tag
                          the system finds          violates completeness

  Tag association         Fraction of tag-to-object A tag attached to the
  precision               matches that are correct  wrong instrument is
                                                    misleading

  Tag report accuracy     Whether                   The explicit tag-check
                          found/missing/ambiguous   deliverable must be
                          categories are correct    trustworthy

  Equipment detection     Correctness and           Major equipment must be
  precision/recall        completeness of major     retained
                          equipment detection       

  Edge precision/recall   Correctness and           The process topology
                          completeness of inferred  must be preserved
                          connections               

  Flow-direction accuracy Correct direction among   Direction is part of
                          evaluated directed        the official
                          connections               requirement

  Graph integrity after   Whether graph nodes/edges Layout must not change
  layout                  are unchanged by drawing  process meaning
                          layout                    

  Human readability       Whether reviewers can     Visual simplification
  rating                  follow the simplified     is part of the
                          flow                      challenge

  Processing time         Time from upload to       Useful, but secondary
                          outputs                   to correctness

  Uncertainty calibration Whether low-confidence    Helps make human review
                          cases are more            useful
                          error-prone than          
                          high-confidence ones      
  -------------------------------------------------------------------------

Do not publish a metric without saying how many drawings were tested and
how the reference was prepared. Do not claim zero errors from a tiny
sample.

## 12.3 Essential test cases

-   Text-based PDF with embedded text.
-   Scanned or raster PDF.
-   A tag present in both PDF and Excel.
-   An Excel tag absent from the drawing.
-   Duplicate or malformed tag.
-   A blurry tag.
-   A line crossing that is not a junction.
-   A real junction.
-   A line connected to equipment through a symbol.
-   A parallel pump pattern.
-   A source with ambiguous flow direction.
-   A graph layout change that must not change the edge set.
-   A held-out drawing or layout that was not hard-coded.

------------------------------------------------------------------------

# 13. What should be in the PPT?

The first-round PPT should sell a believable solution and a clear
execution plan, not a list of technologies.

## Suggested narrative

### Slide 1 --- Problem and user need

Explain the manual work: engineers must simplify customer P&IDs while
retaining the required instruments, equipment and correct process
sequence. Manual tracing is slow and error-prone.

### Slide 2 --- Our solution

Show a simple flow: **P&ID PDF + I/O Excel → extraction → graph +
validation → simplified sketch + tag report.**

### Slide 3 --- What makes us different

Use the proposed USP: - Evidence-linked output. - Tag completeness
checks. - Graph integrity checks. - Uncertainty reporting. - Automatic
sketch generation.

State that these are planned capabilities until implemented and
evaluated.

### Slide 4 --- Architecture and technology

Show the pipeline with clear boundaries: PDF/OCR, Excel parsing,
association, graph, validation, layout, outputs.

### Slide 5 --- MVP and UI

Show planned screens: upload, processing status, sketch preview, tag
report, source-to-output evidence. Use a clearly labelled concept
mock-up if the actual product is not implemented yet.

### Slide 6 --- Implementation and validation

Give the development phases, four-member responsibilities and metrics.
Mention how you will test tag coverage and graph fidelity.

### Slide 7 --- Impact, scale and roadmap

Explain the immediate benefit: less manual redraw effort and easier
review. Longer term: more symbols, multi-page support, revision
comparison and engineering-data integration. Avoid unsupported savings
or accuracy percentages.

## PPT visual guidance

-   Use a clean industrial look: navy, white, teal and one accent
    colour.
-   Show the source diagram and simplified output side-by-side.
-   Use one architecture diagram rather than dense paragraphs.
-   Make the output and tag report the visual centre of the
    presentation.
-   Clearly label prototype screens as "concept" if they are not yet
    functional.
-   Do not use AI-generated diagrams as proof of technical correctness.

------------------------------------------------------------------------

# 14. Demo plan for the jury

A strong demo should prove the central requirements in about 2--3
minutes.

1.  Open the app.
2.  Upload the permitted sample P&ID PDF.
3.  Upload its I/O-list Excel file.
4.  Show that the system identifies the tag inventory.
5.  Click Generate.
6.  Show the automatically created simplified sketch.
7.  Open the tag-check report and point out found and unresolved tags.
8.  Click a tag or equipment item and show its source evidence, if this
    feature is implemented.
9.  Show a validation result or a deliberately ambiguous case that is
    flagged instead of guessed.
10. Download the output.
11. Briefly explain the limitation and the next improvement.

Keep a local backup with dependencies installed. If live OCR or a remote
API is unreliable, use a preprocessed sample run only as a clearly
disclosed fallback---not as a claim that a failed live pipeline worked.

------------------------------------------------------------------------

# 15. Research-paper potential

A research paper needs a specific research question, an implemented
method, a comparison baseline, reproducible experiments and results. A
product with a polished UI is not enough by itself.

## Possible research direction

**Working research question:** Can a tag-constrained, evidence-linked
graph reconstruction pipeline reduce missing-tag and connection errors
during P&ID simplification compared with a baseline that performs
extraction and rendering without explicit completeness and
graph-integrity checks?

This is a hypothesis to test, not a conclusion.

### Potential contributions to investigate

1.  A unified evaluation protocol for tag coverage, graph fidelity, flow
    direction and readability in simplified P&IDs.
2.  A method for using the I/O list as a constraint on extraction and
    output completeness.
3.  Evidence links between each output component/connection and the
    source drawing.
4.  Confidence-aware handling of ambiguous pipe crossings and tag
    associations.
5.  A layout stage that is explicitly tested to preserve the validated
    graph.
6.  A small, carefully documented benchmark based only on data whose
    licences and sharing rules permit it.

### Experimental design

Compare at least: - **Baseline A:** OCR/tag extraction + simple diagram
generation. - **Baseline B:** extraction + graph construction +
deterministic validation. - **Proposed method:** graph validation + I/O
constraints + uncertainty/evidence reporting.

Measure tag recall, tag association precision, edge precision/recall,
flow-direction accuracy, ambiguous-case handling, processing time and
human readability.

The comparison is meaningful only if each system is evaluated on the
same inputs and the reference labels are independently checked.

### Dataset and reproducibility concerns

The organiser says sample P&IDs and I/O lists are for hackathon use only
and must not be shared. Do not publish them in a paper, public
repository or dataset without written permission. For publication,
consider public datasets with compatible licences, synthetic diagrams,
or a permission-cleared evaluation set. Document any synthetic-data
generator and its limitations.

### What would make the work weak?

-   Only describing an architecture without evaluating it.
-   Reporting accuracy on the same sample used to hard-code the
    solution.
-   Comparing against a deliberately weak baseline.
-   Claiming generalisation from one or two drawings.
-   Calling a combination of standard libraries a novel algorithm
    without evidence.
-   Reporting performance metrics without reference annotations or a
    reproducible method.

------------------------------------------------------------------------

# 16. Patent potential and responsible next steps

A patent cannot be promised from a problem idea, a UI, or the use of AI.
Patentability depends on the specific technical invention and the
relevant jurisdiction's requirements, including novelty, inventive
step/non-obviousness, and eligible subject matter. A patent professional
must review the actual claims and prior art.

## How to proceed safely

1.  Keep dated records of the actual algorithm, design decisions and
    experiments.
2.  Search patents and published applications related to P&ID
    digitisation, graph extraction, tag matching and automatic diagram
    simplification.
3.  Compare the proposed technical mechanism---not just the product
    name---with the closest prior art.
4.  Identify a genuinely specific technical improvement supported by
    results.
5.  Discuss ownership and inventorship with the team and institution.
6.  Seek advice from a qualified patent professional or VIT's relevant
    IP/innovation office.
7.  Before publicly disclosing a potentially patentable invention, ask
    the professional about timing and filing strategy. Public disclosure
    can affect rights, especially internationally.

Potential directions to investigate, **not claims of novelty**, include
a new method for enforcing I/O-list completeness during graph
reconstruction, uncertainty-aware topology reconciliation, or a
validated graph-preserving layout constraint. Each requires a prior-art
search and technical evidence.

Useful starting points: - Indian Patent Office:
https://ipindia.gov.in/ - WIPO PATENTSCOPE:
https://patentscope.wipo.int/ - Google Patents:
https://patents.google.com/

Do not put "patent pending" in the PPT unless an application has
actually been filed and the wording is legally appropriate.

------------------------------------------------------------------------

# 17. Risks and mitigation

  -----------------------------------------------------------------------
  Risk                    Why it could hurt the   Mitigation
                          project                 
  ----------------------- ----------------------- -----------------------
  OCR misses tags         Output is incomplete    Use embedded text when
                                                  possible, OCR as
                                                  fallback, and report
                                                  unresolved tags

  Wrong graph connections Process meaning changes Keep graph validation
                                                  separate from
                                                  rendering; test
                                                  junction cases

  LLM hallucinates        Plausible but false     Use structured
                          engineering information evidence, deterministic
                                                  checks and uncertainty
                                                  flags

  Only works on one       Fails the generic       Separate sample
  sample                  requirement             configuration from core
                                                  logic and hold out a
                                                  test drawing

  Too many features       No end-to-end demo      Finish one vertical
                                                  slice first, then add
                                                  features by priority

  Frontend/backend        Components cannot       Agree on JSON schemas
  mismatch                integrate               and API contracts
                                                  before parallel work

  External API/data       Confidential samples    Follow organiser rules;
  concerns                may be exposed          prefer local processing
                                                  where practical

  Performance claims are  Jury may challenge      Report measured results
  untested                credibility             with sample size and
                                                  test conditions

  Patent novelty is       Risk of overclaiming    Perform prior-art
  assumed                                         review and seek
                                                  professional advice

  Generated diagram is    The main output fails   Test readability with
  hard to read            its purpose             people who did not
                                                  build the tool
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 18. Definition of done for the first MVP

The MVP is not done just because the frontend runs.

-   [ ] The user can upload a PDF and an Excel I/O list.
-   [ ] The backend parses the Excel list and preserves original tags.
-   [ ] The PDF is processed automatically.
-   [ ] The tool produces a structured representation of at least the
    supported elements.
-   [ ] A simplified sketch is generated automatically.
-   [ ] The tag report shows found and not-found tags.
-   [ ] The output includes the supported major equipment and I/O tags.
-   [ ] Connections are generated from extracted graph data, not
    manually redrawn.
-   [ ] The validation stage identifies at least the implemented classes
    of uncertainty or error.
-   [ ] The layout stage cannot silently change the graph edges.
-   [ ] The output can be downloaded.
-   [ ] The team can explain the architecture and limitations.
-   [ ] Third-party tools, APIs, models and reused assets are
    documented.
-   [ ] Organiser-provided data is not shared outside the allowed use.

If time is short, state which symbol classes are supported. It is better
to deliver a smaller verified pipeline than to claim universal support
without evidence.

------------------------------------------------------------------------

# 19. Final recommendation

Choose a focused implementation strategy:

**Build the complete path first:** PDF + Excel → extraction → structured
graph → validation → simplified sketch + tag report.

Then make the solution distinctive with **evidence-linked output,
graph-integrity checks, and confidence-aware reporting**. These features
directly reinforce the official requirements for completeness, accuracy,
readability and generic operation.

Do not begin by training a custom detector, adding a chatbot, building a
complex database, or implementing every P&ID symbol family. First
establish that the end-to-end pipeline works on one permitted sample,
then broaden coverage and measure correctness.

The long-term research opportunity is not simply "AI reads engineering
drawings." It is to demonstrate, with repeatable experiments, that the
proposed constraints, evidence links and validation mechanisms improve
the reliability of automatic P&ID simplification.

------------------------------------------------------------------------

# 20. Sources and further reading

## Official challenge source

-   VIT Code_Apex 3.0 --- Emerson Project UNTANGLE problem statement
    (organiser-provided PDF; follow the event's restrictions on sample
    data).

## Research papers

1.  Rahul et al., *Automatic Information Extraction from Piping and
    Instrumentation Diagrams* (2019): https://arxiv.org/abs/1901.11383
2.  Mani et al., *Automatic Digitization of Engineering Diagrams Using
    Deep Learning and Graph Search* (CVPR Workshops, 2020):
    https://doi.org/10.1109/CVPRW50498.2020.00096
3.  Paliwal et al., *Digitize-PID: Automatic Digitization of Piping and
    Instrumentation Diagrams* (2021 preprint):
    https://arxiv.org/abs/2109.03794
4.  *End-to-end digitization of image format piping and instrumentation
    diagrams at an industrially applicable level* (Journal of
    Computational Design and Engineering, 2022):
    https://academic.oup.com/jcde/article/9/4/1298/6611631
5.  Stürmer et al., *Transforming Engineering Diagrams: A Novel Approach
    for P&ID Digitization using Transformers* (2024 preprint):
    https://arxiv.org/abs/2411.13929
6.  *Hybrid approach for comprehensive recognition of line objects
    contained in high-density P&IDs using deep learning and rules*
    (2026):
    https://www.sciencedirect.com/science/article/abs/pii/S0098135426000244
7.  *From P&ID Drawings to Process Graphs: A Multimodal Language Model
    Approach* (2026 preprint): https://arxiv.org/abs/2607.19568

## Commercial product context

-   Hexagon Smart P&ID: https://hexagon.com/products/smart-p-id
-   AVEVA engineering products:
    https://www.aveva.com/en/products/engineering/

## Patent search starting points

-   Indian Patent Office: https://ipindia.gov.in/
-   WIPO PATENTSCOPE: https://patentscope.wipo.int/
-   Google Patents: https://patents.google.com/

------------------------------------------------------------------------

*Prepared as a planning guide. Validate all technical claims and results
against the actual permitted inputs before using them in the submission
or a research paper.*
