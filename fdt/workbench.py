"""Build an offline workbench for selected calibrated MANUAL panels."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import make_plan
from manual_digitize import digitizer_style, panel_data


def build(run, proposals):
    geometry, identities, _, _ = make_plan.load_confirmations(str(run), None, None, None)
    panels = [panel_data(run, proposal, geometry, identities) for proposal in proposals]
    for panel in panels:
        (v0, p0), (v1, p1) = panel["ticks"]
        if not all(map(math.isfinite, (v0, p0, v1, p1))) or v0 == v1:
            raise ValueError(f'{panel["id"]}: invalid calibration')
    serialized = json.dumps(panels, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(serialized.encode()).hexdigest()
    template = Path(__file__).with_suffix(".html").read_text(encoding="utf-8")
    script = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    payload = json.dumps({"key": key, "panels": panels}, ensure_ascii=False)
    template = template.replace("/* DIGITIZER_CSS */", digitizer_style())
    return template.replace("/* WORKBENCH_JS */", script).replace(
        "/* WORKBENCH_DATA */", payload.replace("<", "\\u003c"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--panel", nargs="+", required=True, help="Confirmed Proposal_IDs")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(set(args.panel)) != len(args.panel):
        parser.error("Supply each panel once")
    try:
        html = build(args.run, args.panel)
        with args.out.open("x", encoding="utf-8") as output:
            output.write(html)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
