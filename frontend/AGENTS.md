<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- Keep the UNTANGLE workspace at the index route with focused diagram components and browser-safe sample data; this makes the demo immediate and keeps diagram interactions isolated.
- Use D3 shape functions for process connectors and custom SVG for engineering symbols and source linework; this preserves crisp, selectable, synchronised diagrams at every zoom level.
- Export diagrams entirely in the browser, loading PDF generation only when requested; this keeps source data local and avoids unnecessary server dependencies.
- Demo clarification and manual-location changes are session state, not persisted project edits; this workspace demonstrates review interactions without claiming real AI processing.
