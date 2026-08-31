"""
run_pipeline.py

The single entry point for processing ONE COMSOL export file into a
named artifact zip. Written to be exactly what GitHub Actions calls AND
exactly what you run locally - there is no branching on environment
anywhere in this file. The only environment-aware code lives in
fetch_input.py, called once at the top.

Usage:
    python run_pipeline.py --input path/or/drive-id/or/url \
                            --physics mixed_convection \
                            --params Re Ri

Output:
    artifacts/<input file stem>.zip
        plots/*.png              - isotherms, streamlines, heatlines, Nu(X)
        manifest.json            - case name, params, derived scalars,
                                    and a map of plot_name -> filename,
                                    so report_from_artifacts.py can
                                    assemble a Word report later without
                                    re-deriving anything.

Currently wired for mixed_convection (isotherms/streamlines/heatlines/Nu).
For a different physics: change --physics, register its quantities in
derived_quantities.py, and add its plot calls in build_plots() below -
the zip/manifest/CLI plumbing doesn't change.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fetch_input import resolve_input
from data_loader import load_export
from derived_quantities import derive
from plot_from_csv import plot_contour


def build_plots_mixed_convection(record, out_dir: Path) -> dict:
    """Returns {plot_name: filename} for the manifest."""
    plots = {}

    x_col, y_col = record.coord_cols[0], record.coord_cols[1]
    theta_col = "T" if "T" in record.field_cols else "theta"

    # Isotherms straight from the exported field - no derivation needed.
    xs = sorted(record.df[x_col].unique())
    ys = sorted(record.df[y_col].unique())
    theta_grid = record.df.pivot_table(index=y_col, columns=x_col, values=theta_col) \
                            .reindex(index=ys, columns=xs).values
    plots["isotherms"] = plot_contour(xs, ys, theta_grid, "Isotherms",
                                       out_dir / "isotherms.png").name

    # Streamlines + heatlines - these ARE derived (see derived_quantities.py)
    xs2, ys2, psi, pi = derive(record, "mixed_convection", "stream_and_heat_function")
    plots["streamlines"] = plot_contour(xs2, ys2, psi, "Streamlines (psi)",
                                         out_dir / "streamlines.png").name
    plots["heatlines"] = plot_contour(xs2, ys2, pi, "Heatlines (Pi)",
                                       out_dir / "heatlines.png").name

    return plots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True,
                         help="Local path, Google Drive URL/ID, or http(s) URL")
    parser.add_argument("--physics", default="mixed_convection")
    parser.add_argument("--params", nargs="+", default=["Re", "Ri"],
                         help="Parameter names to recover from the export's header/filename")
    parser.add_argument("--case-name", default=None,
                         help="Defaults to the input file's stem")
    parser.add_argument("--artifacts-dir", default="artifacts")
    args = parser.parse_args()

    local_path = resolve_input(args.input)
    case_name = args.case_name or local_path.stem

    work_dir = Path("output") / case_name
    plots_dir = work_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    record = load_export(local_path, param_names=args.params)
    print(f"[run_pipeline] loaded '{local_path.name}' - params: {record.params}, "
          f"fields: {record.field_cols}")

    derived_scalars = {}
    if args.physics == "mixed_convection":
        derived_scalars["grashof"] = derive(record, "mixed_convection", "grashof")
        derived_scalars["nusselt_avg"] = derive(record, "mixed_convection", "nusselt_avg")
        plot_map = build_plots_mixed_convection(record, plots_dir)
    else:
        # Extend here for other physics - see derived_quantities.py's
        # PHYSICS_REGISTRY template for the pattern.
        raise NotImplementedError(
            f"No plot pipeline wired for physics='{args.physics}' yet. "
            "Register its derived quantities in derived_quantities.py and "
            "add a build_plots_<physics>() function above."
        )

    manifest = {
        "case_name": case_name,
        "source_file": local_path.name,
        "physics": args.physics,
        "params": record.params,
        "derived": derived_scalars,
        "plots": plot_map,   # plot_name -> filename (relative to plots/)
    }
    with open(work_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[run_pipeline] manifest: {json.dumps(manifest, indent=2)}")

    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    zip_base = artifacts_dir / case_name  # shutil appends .zip
    zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=work_dir)
    print(f"[run_pipeline] wrote {zip_path}")


if __name__ == "__main__":
    main()