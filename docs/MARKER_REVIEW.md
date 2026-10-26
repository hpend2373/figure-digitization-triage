# Source review for missing and overlapping markers

Use this procedure before asking a person to resolve an unread or disputed plot.
The PDF inspection helper produces source evidence proposals. It does not name
series, calibrate outcomes, register a reader, approve values, or write accepted
data. Keep publication files and actual review answers outside the public tree.

## Review sequence

1. Build an inventory from the original figure and caption. Count observed marks
   per outcome and series, including overlapping locations. Keep fitted curves,
   regression intercepts, individual traces, legend samples, and group means
   distinct. Missing values remain blank; never match an expected count by copying.
2. Inspect the full source page as well as a native-resolution crop. Check whether
   an apparently clipped graph is a second outcome entering the crop. Calibrate
   only from the target axis. An unticked axis stays in pixels unless the person
   explicitly chooses a documented axis interpretation.
3. For vector PDFs, inspect separate marker paths and paint order before declaring
   a covered marker unreadable. `pdf_marker_evidence.py` preserves both filled
   paths even when their centers coincide. An adjacent outline is attached to its
   filled glyph. A stroke-only circle and an XObject are reported as coverage limits.
4. Keep a source hash, page, operation range, fill, path and center for each
   selected glyph. Re-verify that evidence against the same PDF bytes. Page-space
   coordinates and raster pixels are different systems; use the declared media
   box, DPI and raster origin for conversion. Check the conversion against visible
   known marks. A path bounds center is not a claim of arbitrary numeric precision.
5. Read measured x and y as a pair with a stable point identifier. Several outcomes
   inside one panel remain distinct outcomes. If the extraction contract cannot
   represent them, retain a separate source-coordinate proposal packet rather than
   editing compiled manifests or inventing series/positions to fit the grid.
6. Put each proposed point on the source figure. Add new identifiers after existing
   ones. Separate overlapping labels with leader lines. Numbering or neutral ink
   identifies coordinates; it does not introduce a biological group. Unknown series
   remain unassigned and carry an analysis hold.
7. Have independent checks inspect actual attached source images and actual
   overlays. Record both agreements and limits. Reconcile disagreements from the
   source, then inspect the changed overlay again. Passing counts or hashes alone
   do not establish marker completeness.
8. Show the person only new or changed cards. Review forms start blank, show all
   cards by default, and keep a card visible after approval. Direct entry requires
   an explicit point selection. A click near another series or outcome is a
   mapping conflict: preserve the original click and ask about the proposed
   mapping instead of silently overwriting the selected row.
9. Validate submitted identities, dates, required checks, source/overlay hashes,
   exact numeric scope and every pixel-to-value calculation. Changed packets get
   new review subjects. Existing signatures do not transfer to new points, labels,
   axis interpretations or measurements. Uncalibrated coordinates stay outside
   numeric approval. Do not infer missing error ends or convert uncertainty types.
10. Rehearse acceptance in a copy, compare accepted bytes with the actual run, and
    prove a clean rerun writes nothing. Preserve raw inputs and historic approvals.
    Report panel counts separately from scalar coordinates and preserve analysis
    holds. Numerical approval does not authorize inclusion or variance weighting.

## Inspect a source PDF

Install the optional PDF backend from `requirements-intake.txt`, then run:

```sh
python3 fdt/pdf_marker_evidence.py /private/source.pdf --page 1 --out /private/proposals.json
python3 tests/test_pdf_marker_evidence.py
```

The JSON is `PROPOSAL_ONLY`, with `human_review_required=true` and
`pooling_eligible=false`. The output is a JSON report; the command refuses to
overwrite an existing file or to write a CSV. The helper inspects filled closed
four-cubic paths in page content. It does not inspect XObject content, infer
series membership, or prove that every circular path is a data marker. Rotated
pages, encrypted files, unsupported color spaces, and invalid graphics states
fail explicitly. Inspect raster-only material from the original pixels instead.
Device-color initialization follows the color operators in section 4.5 of the
[Adobe PDF Reference](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.6.pdf).

For a difficult overlap, an optional inspection copy may hide the covering glyph
to expose the source path beneath it. Label it as an inspection copy, record the
omitted operation ranges, and keep the published source unchanged. It provides
evidence of an existing glyph; it must not draw a new mean or fit a hidden value.

The public tests use a tiny synthetic PDF with known centers and paint order.
Publisher-source forward checks stay private with their hashes and receipts.
Run the mutation matrix only in a scratch checkout of the source code.
