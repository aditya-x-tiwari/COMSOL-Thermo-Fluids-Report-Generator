COMSOL Validation Automation
Automates: apply a case's boundary conditions to an existing geometry/mesh
-> solve -> export data -> re-plot consistently -> assemble a Word report
comparing your COMSOL results against a published paper's figures,
side by side.
Running per-case, and packaging for GitHub Actions
Each COMSOL export becomes its own zip, named after the file:
Bash
--input accepts a local path, a Google Drive URL/ID, or an http(s)
URL - src/fetch_input.py resolves whichever you give it to a local
path, and that's the ONLY environment-aware code in the project.
run_pipeline.py itself runs identically locally or in CI.
Don't commit COMSOL exports to git. They're large; GitHub's repo
and Actions limits aren't built for that. Keep the data file in Drive
(or any storage), and let the workflow download it fresh each run:
Bash
See .github/workflows/comsol-pipeline.yml. It downloads the file onto
the runner's disk, runs run_pipeline.py exactly as above, and uploads
only the resulting zip (a few hundred KB) as a build artifact - the
downloaded export is discarded when the runner shuts down.
As more cases come in, each run produces another named zip. Collect
however many you want, then build the report from all of them:
Bash
This reads each zip's manifest.json (case name, params, derived
quantities, which PNG is which) - that manifest is what makes
"just point it at a folder of zips + the paper PDF" work reliably.
Without it, matching plots to cases from filenames alone is guesswork;
with it, the report builder needs zero physics-specific logic. You
still write figure_map.json once per paper (page + crop box per
figure - same bbox mechanism as fig_extractor.py earlier), since
matching a case to which paper figure it validates against isn't
something that can be inferred automatically.
Recommended workflow (read this first)
Two ways to run this:
Post-processing only (recommended) — build your 4 case variants
and Re/Ri parametric sweep natively in COMSOL Desktop (Export > Data,
tick "Include parameter values in filename"), click Compute All, then
point Python at the output folder: src/data_loader.py +
src/derived_quantities.py. No API scripting, no node-tag guessing.
COMSOL handles solving/convergence (it's better at that than an
external loop); Python only computes Nu/Gr/streamfunction/heatfunction
and builds the report. Use this unless you have a specific reason
not to.
Live-driven (main_sweep.py + comsol_driver.py) — Python
controls COMSOL directly via MPh. Worth the extra fragility only if
you need many structural (not just parameter) variants, or unattended
runs with no GUI at all.
Why: the export schema
Export only the primary solved fields + coordinates — never
derived quantities. For mixed convection: X, Y, u, v, T. Everything
else (Nu, Gr, streamfunction, heatfunction) is computed from those five
columns plus the run's Re/Ri in derived_quantities.py. This
generalizes to any physics — see the PHYSICS_REGISTRY template in
that file for adding e.g. drag/lift for external flow, or Sherwood
number for species transport: same loader, same report builder, just a
new small dict of formulas.
Python
load_export reads Re/Ri straight from COMSOL's own header comment
lines (or the filename, as a fallback) — so the "fundamental values" a
file needs are just: coordinates, primary fields, and the parameter
values COMSOL already writes when the export is tied to a parametric
solution. Nothing else has to be captured manually.
Setup
Bash
Requires COMSOL 6.3 installed locally (any base license — no MATLAB
LiveLink needed). MPh talks to COMSOL through its built-in Java API.
One-time model prep (do this once per geometry, in COMSOL Desktop)
The script does not blindly guess your model's internal structure.
Before running it on a geometry for the first time:
Build the geometry, physics, mesh, and study normally in COMSOL Desktop.
Rename the boundary condition features you'll want to swap between
cases (e.g. rename a Temperature node to temp_top instead of the
default temp1) — right-click the node -> Rename.
Add Table nodes under Results -> Derived Values for whatever you
need exported (local Nusselt number, entropy generation, etc.), and
note their tags.
If you want image exports too, add Export nodes under
Results -> Export for each plot group.
To find the exact tags fast: Developer tools -> Application Builder ->
New Method -> Record, then change a BC by hand once. It generates Java
showing you the real tag names — copy them into cases.yaml.
Save as your template .mph.
Running
Bash
The wizard will:
Load your template (or offer to build a bare-bones rectangular
enclosure from scratch if you don't have one yet — see caveat below)
Let you run all cases, pick specific ones, or tweak a BC value first
Solve each case, export CSVs/images, re-plot, and build
output/validation_report.docx
Editing cases
Open config/cases_example.yaml (copy it per project). Each case lists:
boundary_conditions: which feature tag to change and how
export.tables / export.images: what to pull out after solving
paper_figure: path to a cropped image of the paper's original
figure, placed side by side with your result in the report
Known limitations / what's intentionally NOT automated
From-scratch geometry building (src/scratch_builder.py) only
covers a plain rectangular domain with a couple of physics presets.
It builds the shell — you still finish BC values and export nodes
in COMSOL Desktop once, then save it as a template. Scripting a
genuinely arbitrary geometry/physics builder isn't realistic to
maintain for a two-paper validation project.
Swapping a boundary condition's type (e.g. cold wall -> adiabatic)
is easiest if both features already exist in the template with one
active/inactive (feature.active(True/False)), rather than trying to
change a feature's type at runtime. comsol_driver.py has a comment
flagging this — adjust apply_case() to match how you set up the
template.
CSV column indices in plot_from_csv.py assume a simple 2-column
table (x, value). Update x_col/y_col if your table export has a
different layout.
The paper's original figures aren't scraped automatically — crop
them yourself from the PDF into config/paper_figures/ (copyright:
don't redistribute these outside your own report).
The Re/Ri sweep vs. the 4 discrete cases
Don't script Re and Ri as BC edits. Define them as COMSOL Global
Parameters in the template (Global Definitions -> Parameters):
Code
Point your BC features at Th, Tc, vw (not literal numbers). Then
main_sweep.py sweeps Re/Ri with driver.set_parameters({"Re":.., "Ri":..})
resolve - fast, no feature editing. Python's comsol_driver.apply_case()
is only used for the genuinely discrete part per case: which BC feature
is active (cold vs adiabatic) and the sign of vw (up/down) - run once
per case, before the sweep starts.
Heatlines aren't a COMSOL output - they're computed in Python
Streamlines/isotherms/Nusselt number are direct COMSOL exports. Heatlines
are not - src/heatline_calculator.py implements the paper's Eq. (6)-(7)
integration from an exported (X, Y, U, V, theta) grid. Validated against
an analytic test case (max error 2e-4). Use a COMSOL Grid dataset
(not the default point cloud) for the export so the data lands on a
regular grid this expects.
Extracting the paper's own figures automatically
src/fig_extractor.py renders a PDF page (pdftoppm) and crops a pixel
bounding box out of it (Pillow) - no manual screenshotting. You find each
bbox once by rendering the page and eyeballing coordinates in an image
viewer, then it's fully scripted from there. Tested against the actual
Biswas & Manna PDF. Feed the resulting PNGs into report_builder.py's
paper_figure.image_file the same way as a manual crop.
Architecture
Code