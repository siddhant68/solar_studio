# Research for Module 02 (terrain)

26 October 2026. Machine-readable record: `research/SOURCES.json`. Runtime probe: `research/probes/library_probes.py` with output `research/library-probes.json`. Every statement below carries its authority:
- **source-read**: code read at a pinned commit, not executed;
- **runtime-probe**: a library installed and called in an isolated environment;
- **repository-search**: a pinned commit searched for a feature;
- **not-inspected**: named for context only.

None of this is evidence that our future code is correct. The acceptance fixtures are the evidence for that.

## What existing open-source tools actually implement

### PVPlant (FreeCAD workbench), `7852ee5`, source-read

PVPlant is the only open-source PV layout tool screened that does terrain-following placement. Its licence status is unclear: the file headers say LGPL-2-or-later, but there is no licence file. We read it for concepts and reuse no code.

What it does:
- **Terrain mesh.** Delaunay over all survey points inside a boundary, then a filter on triangle edge length and angle (`PVPlantCreateTerrainMesh.py:136-146`). Rejected faces keep zero-initialised vertices, so the mesh contains degenerate triangles at the origin rather than holes.
- **Grid import.** It reads ESRI ASCII grids and interpolates CSV points with a thin-plate RBF onto a grid spanning the whole bounding box (`Utils/importDEM.py`), which extrapolates beyond the survey. For `XLLCENTER` it subtracts half the grid width instead of half a cell (lines 58-59). In our probe GDAL puts that grid 2 m (x) and 1 m (y) away from PVPlant's formula.
- **No-data handling.** Elevations are scaled ×1000 before being compared with the unscaled `NODATA_VALUE`, so -9999 cells are not filtered out (`PVPlantTerrain.py:327, 356`).
- **Placement.** "Adjust to terrain" (`PVPlantPlacement.py:771-874`) projects points along each table's centre line onto the mesh. It sets the frame's z to the mean of two projected points and rotates the frame to follow the ground, with an optional regression trend. It does not check clearance over the whole footprint, and projection misses are silently dropped.
- **Supports.** Piles are parameters with defaults (seven poles, 3000 mm length; `PVPlantRack.py:885-898`), not derived quantities.
- **Earthworks.** There is an earthworks cut/fill tool, which is grading and outside Module 02.

**Consequences for the design:** explicit TIN faces, no implicit triangulation, masked no-data handling, GDAL-compatible registration, a full-footprint clearance computed at overlay vertices, and supports from a stated model (fixtures T03, T04, T05 and T06 cover these failure modes).

### pvlib-python, `d6075f6`, source-read

pvlib's terrain-aware functions (`tracking.calc_axis_tilt`, `calc_cross_axis_tilt`, `shading.ground_angle`) assume **one uniform planar slope**. For example, tan(axis tilt) = cos(Δγ)·tan(slope tilt), from NREL/TP-5K00-76626. There is no DEM or TIN handling. pvlib is useful as an independent oracle for uniform-slope geometry in the later reorientation milestone, and is not needed for vertical lift.

### Agrivoltaic garden planner, `43118b3`, repository-search

The planner uses a single site elevation from the weather record, for sun position only. It has no terrain surface or terrain-following placement.

### PROJ through pyproj 3.7.2 / PROJ 9.5.1, runtime-probe

Offline and without the EGM96 grid, converting WGS 84 ellipsoidal height to EGM96 height silently returns the input: 100 m in, 100 m out. The accuracy is -1 (unknown), the description says "ballpark vertical transformation", and no warning or error is raised. This stays true with `only_best=True`, with `PROJ_ONLY_BEST_DEFAULT=YES` and with `errcheck=True`. Only `TransformerGroup` warns that the best operation is unavailable.

**Consequence:** Module 02 performs no vertical transformation. Datum identity is checked, and a mismatch is an error.

### SciPy 1.16.2, runtime-probe

Delaunay + `LinearNDInterpolator` over points surrounding an unsurveyed 4 × 4 m gap triangulate the gap and return a finite elevation at its centre. Only points outside the convex hull return NaN.

**Consequence:** coverage is exactly the supplied triangles, and there is no automatic triangulation in T1.

### GDAL through rasterio 1.4.3 / GDAL 3.9.3, runtime-probe

- Masked reads mark no-data cells.
- Unmasked sampling returns the raw -9999.
- GeoTIFFs default to `AREA_OR_POINT=Area`, so cell centres are half a cell from the corner.
- ESRI ASCII `XLLCENTER` is converted correctly.

The manylinux wheel bundles GDAL with GEOS (LGPL-2.1), OpenSSL's libcrypto, curl, HDF5 and other libraries. **Consequence:** the DEM adapter is a separate, optional milestone (T3) that uses masked reads and explicit registration, with its dependency footprint reviewed by the owner.

### Screened but not inspected

PDAL (point clouds), WhiteboxTools (slope/aspect), CGAL (constrained triangulation; GPL/LGPL by package), RichDEM (GPL-3) and the LandXML 1.2 TIN format are listed with their claimed licences in `SOURCES.json`. Commercial terrain-following tools (PVcase, PVsyst, SolarFarmer and others) were not inspected and are not dependencies.

## REA decision

REA artifact and runtime analysis answers questions about **shipped behaviour of a built artifact**. For the first terrain milestones:
- The open-source tool that does terrain-following (PVPlant) is Python source inside a desktop CAD application. Ordinary source reading answers our questions about it, as recorded above. It is not a built web artifact, and installing FreeCAD would add nothing the fixtures do not already test.
- The Module 01 browser reference has no terrain behaviour, so there is nothing to observe.
- Commercial terrain tools are native desktop or CAD plug-ins. They are not cloud-compatible REA targets and must not become dependencies.

**No REA work is proposed for T1–T3.** REA would be proposed only for a concrete question, such as how a specific shipped web application treats no-data cells under a rack, where:
- the owner names a publicly buildable web artifact with terrain placement;
- the answer would change a contract decision;
- the evidence plan is like Module 01's: a pinned build recipe, file hashes, REA static analysis of the relevant chunks, `capture_browser_scenario` for a held terrain-import scenario, and `observe_web_execution` around the placement call, all in the cloud container.

A missing native CAD analysis tool is not a blocker for any milestone.

## Reproducing the probes

```sh
uv venv --python 3.12 /tmp/terrain-probes
VIRTUAL_ENV=/tmp/terrain-probes uv pip install pyproj==3.7.2 scipy==1.16.2 numpy==2.3.4 rasterio==1.4.3
PROJ_NETWORK=OFF /tmp/terrain-probes/bin/python -I research/probes/library_probes.py /tmp/library-probes.json
```

The probe installs no geoid grids and keeps PROJ networking off, as a default offline deployment would.
