"""Build an offline point-entry page for a confirmed MANUAL panel."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path

from PIL import Image

import make_plan as plan
from geometry_proposer import calibration_from
from page_bits import esc


def panel_data(run, proposal_id, geometry, identities):
    identity = identities[proposal_id]
    frame = geometry[proposal_id]
    if (identity["Human_Verification_Status"] != "CONFIRMED"
            or identity["Read_Route"] != "MANUAL"
            or not calibration_from(frame)):
        raise ValueError("A confirmed identity and calibrated MANUAL panel are required")
    if not identity["Mark_Type"].startswith(("BAR", "LINE")):
        raise ValueError("This page supports bar and line summary marks")
    raster = (run / identity["Raster"]).resolve()
    if not raster.is_relative_to(run.resolve()):
        raise ValueError("Raster must be inside the run")
    raw = raster.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != identity["Raster_SHA256"] or digest != frame["Raster_SHA256"]:
        raise ValueError("Raster fingerprint differs from the confirmed records")
    x0, x1, y0, y1 = (round(float(frame[key])) for key in
                      ("Panel_X0", "Panel_X1", "Panel_Y0", "Panel_Y1"))
    with Image.open(io.BytesIO(raw)) as source:
        if not (0 <= x0 < x1 < source.width and 0 <= y0 < y1 < source.height):
            raise ValueError("Confirmed panel is outside the raster")
        crop = io.BytesIO()
        source.crop((x0, y0, x1 + 1, y1 + 1)).save(crop, format="PNG")
    cells = [[series["name"].strip(), position["label"].strip()]
             for series in json.loads(identity["Series"])
             for position in json.loads(identity["X_Labels"])]
    if not cells or any(not all(cell) for cell in cells) or len(set(map(tuple, cells))) != len(cells):
        raise ValueError("Panel must have unique named cells")
    return {"id": proposal_id, "hash": digest, "cells": cells,
            "columns": plan.READING_FIELDS, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "ticks": calibration_from(frame), "outcome": identity.get("Outcome_Name", ""),
            "unit": identity.get("Unit", ""), "bar_top": identity.get("Bar_Top_Definition", ""),
            "image": base64.b64encode(crop.getvalue()).decode("ascii")}


def build(run, proposal_id):
    geometry, identities, _, _ = plan.load_confirmations(str(run), None, None, None)
    panel = panel_data(run, proposal_id, geometry, identities)
    x0, y0, x1, y1 = (panel[key] for key in ("x0", "y0", "x1", "y1"))
    png = panel.pop("image")
    data = json.dumps(panel).replace("<", "\\u003c")
    logic = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Manual plot digitizer</title>
<style>
body {{ font: 16px system-ui; margin: 2rem; color: #18303e; }}
label,button {{ display: inline-block; margin: .4rem; }}
svg {{ display: block; width: 100%; max-width: 1200px; height: auto; cursor: crosshair; }}
</style>
<h1>Manual plot digitizer</h1>
<p>{esc(proposal_id)} · {esc(panel["outcome"])} · {esc(panel["unit"])}
 · {esc(panel["bar_top"])}</p>
<p>Select a cell and click its bar end or marker center. Place the visible error ends separately.
Leave unreadable ends blank. Download your pixel readings before closing the page.</p>
<label>Cell <select id="cell"></select></label>
<label>Mark <select id="mark"><option value="mean">Center or bar end</option>
<option value="upper">Top error end</option><option value="lower">Bottom error end</option></select></label>
<button id="clear">Clear selected mark</button>
<svg id="plot" viewBox="{x0 - .5} {y0 - .5} {x1 - x0 + 1} {y1 - y0 + 1}"
     aria-label="Panel for manual digitization">
<image href="data:image/png;base64,{png}" x="{x0 - .5}" y="{y0 - .5}"
 width="{x1 - x0 + 1}" height="{y1 - y0 + 1}"/><g id="marks" pointer-events="none"/></svg>
<label>Reader ID <input id="reader"></label><label>Date <input id="date" type="date"></label>
<button id="download" disabled>Download pixel readings</button><p id="status" role="status"></p>
<script type="application/json" id="config">{data}</script><script>{logic}</script></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--panel", required=True, help="Proposal_ID from identity_decisions.csv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        page = build(args.run, args.panel)
        with args.out.open("x", encoding="utf-8") as output:
            output.write(page)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
