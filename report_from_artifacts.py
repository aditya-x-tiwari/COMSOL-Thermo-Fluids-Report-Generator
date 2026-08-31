"""
report_from_artifacts.py

Answers "can I just point Python at a folder of zips + the paper PDF
and get a report" - yes, PROVIDED each zip has a manifest.json (written
by run_pipeline.py). The manifest is what makes this reliable: without
it, matching "which PNG is the isotherms plot for which case" from
filenames alone is guesswork. With it, this script needs zero physics
knowledge - it just reads what run_pipeline.py already recorded.

Usage:
    python report_from_artifacts.py --artifacts-dir artifacts \
        --paper path/to/paper.pdf \
        --figure-map figure_map.json \
        --output output/validation_report.docx

figure_map.json (you write this once per paper - see example below):
    {
      "case1_Re100_Ri10": {
        "pdf_page": 7,
        "bbox": [150, 120, 480, 300],
        "label": "Fig. 3, Ri=10, Re=100"
      },
      ...
    }

One entry per case_name (must match manifest.json's case_name / the
zip's filename stem). If a case has no entry, its row in the report
just omits the paper-figure column - it still gets the COMSOL plots.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from fig_extractor import extract_paper_figure
from report_builder import build_report


def load_manifests(artifacts_dir: Path, extract_dir: Path) -> list[dict]:
    manifests = []
    for zip_path in sorted(artifacts_dir.glob("*.zip")):
        case_extract_dir = extract_dir / zip_path.stem
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(case_extract_dir)
        manifest_path = case_extract_dir / "manifest.json"
        if not manifest_path.exists():
            print(f"[report_from_artifacts] WARNING: {zip_path.name} has no "
                  f"manifest.json, skipping (was it made by run_pipeline.py?)")
            continue
        manifest = json.loads(manifest_path.read_text())
        manifest["_extract_dir"] = case_extract_dir
        manifests.append(manifest)
    return manifests


def build_case_config_and_plots(manifests: list[dict], pdf_path: str | None,
                                 figure_map: dict, paper_fig_dir: Path):
    """Reshapes manifests into the (config, case_plot_paths) shape
    report_builder.build_report() already expects."""
    config = {"cases": [], "report": {"title": "COMSOL Validation Report"}}
    case_plot_paths = {}

    for m in manifests:
        name = m["case_name"]
        plots_dir = m["_extract_dir"] / "plots"
        plot_paths = {pname: plots_dir / fname for pname, fname in m["plots"].items()}
        case_plot_paths[name] = plot_paths

        derived_str = ", ".join(f"{k}={v:.4g}" for k, v in m.get("derived", {}).items())
        params_str = ", ".join(f"{k}={v:g}" for k, v in m.get("params", {}).items())
        description = f"{params_str} | {derived_str}" if derived_str else params_str

        case_entry = {"name": name, "description": description}

        fig_spec = figure_map.get(name)
        if fig_spec and pdf_path:
            out_path = paper_fig_dir / f"{name}_paper.png"
            extract_paper_figure(pdf_path, fig_spec["pdf_page"], tuple(fig_spec["bbox"]),
                                  str(out_path))
            case_entry["paper_figure"] = {"label": fig_spec.get("label", "Paper figure"),
                                           "image_file": str(out_path)}

        config["cases"].append(case_entry)

    return config, case_plot_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--paper", default=None, help="Path to the source paper PDF")
    parser.add_argument("--figure-map", default=None,
                         help="JSON file mapping case_name -> {pdf_page, bbox, label}")
    parser.add_argument("--output", default="output/validation_report.docx")
    args = parser.parse_args()

    figure_map = {}
    if args.figure_map and Path(args.figure_map).exists():
        figure_map = json.loads(Path(args.figure_map).read_text())

    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = Path(tmp) / "extracted"
        paper_fig_dir = Path("output/paper_figures")
        paper_fig_dir.mkdir(parents=True, exist_ok=True)

        manifests = load_manifests(Path(args.artifacts_dir), extract_dir)
        if not manifests:
            raise SystemExit(f"No valid case zips (with manifest.json) found in "
                              f"{args.artifacts_dir}")

        config, case_plot_paths = build_case_config_and_plots(
            manifests, args.paper, figure_map, paper_fig_dir)

        build_report(config, case_plot_paths, args.output)


if __name__ == "__main__":
    main()