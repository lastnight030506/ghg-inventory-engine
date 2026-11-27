# Changelog

All notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

Five input-boundary defects, each found by running the tool against files a
human would plausibly produce rather than against its own fixtures:

- **The installed package could not find its own data.** Default paths were
  CWD-relative (`data/activity/...`), so `pip install ghg-inventory-engine && ghg
  inventory` failed with "factor register not found" anywhere outside the repo
  root. Data now ships inside the wheel and is resolved by `ghg.paths`, which
  checks `$GHG_DATA_DIR`, then `./data`, then the packaged copy.
- **A malformed CSV crashed with a traceback.** An unclosed quote leaves a row
  short, `csv` yields `None` for the missing cells, and `parse_quantity` raised
  `AttributeError: 'NoneType' object has no attribute 'strip'`. Short rows are now
  padded so the validators report "blank field" with a line number.
- **A header with surrounding spaces was rejected.** ` site ` is still the site
  column; Excel pads header cells routinely. Header names are stripped.
- **A duplicated column was silently resolved.** `csv.DictReader` keeps the last
  of two same-named columns, so which value won was invisible. Now rejected as
  ambiguous.
- **A factor `scope` of `' 1 '` was order-dependent.** Numeric fields are stripped
  before `int()`/`float()`, and thousands separators are tolerated.

Both loaders now share one reader (`ghg/_csv.py`) so the hardening cannot drift
between them.

### Added

- `ghg.paths` — data resolution with `$GHG_DATA_DIR` override, plus tests for
  every branch.
- `installed-package` CI job: builds the wheel, installs it into a clean venv, and
  runs the CLI from a directory with no `data/` of its own.
- `Makefile` with `make check` matching CI.
- 18 tests covering the defects above (102 → 120).

## [1.0.0] — 2026-11-23

### Added

- **Inventory engine.** Activity CSV → validated per-gas ledger → Scope 1/2/3
  totals, joined to a cited emission-factor register. Fails closed on an
  unregistered source, a unit mismatch, a missing citation, a blank or implausible
  publication year, an unknown gas, or a duplicate `(source, gas)` key.
- **Emission factors as data.** IPCC 2006 Tables 1.2/1.4 and 2.3 (manufacturing,
  not energy industries), Vietnam grid factor, GLEC/DESNZ freight factors, each
  row carrying its citation and year. IPCC AR6 WG1 GWP100; combustion methane is
  classified non-fossil per GHG Protocol guidance.
- **Dispersion screening.** Gaussian plume with Pasquill–Gifford stability,
  Briggs rural and urban coefficients, Holland plume rise, Briggs stack-tip
  downwash, ground reflection and mixing-lid reflection with the uniform-mixing
  limit at σ_z > 1.6·L.
- **Plume footprint map.** Vectorised concentration field contoured over the
  downwind zone.
- **Reports.** One Markdown source rendered to Markdown and A4 PDF, with an
  auditable ledger, a provenance table, and a boundary statement.
- **Scenario comparison.** Year-over-year change decomposed into activity, factor
  and interaction effects; location-based and market-based Scope 2 side by side.
- **Packaging.** Dockerfile, 86 initial pytest checks, CI with a coverage floor,
  a stale-report check, and the Handover Report.

### Fixed (before first release)

- Stack-tip downwash was applied backwards — raised the exit velocity instead of
  lowering the stack height by `2[(vs/u) − 1.5]d`, which under-predicted
  ground-level concentration for low-velocity stacks.
- Urban wind-profile exponents were applied to rural sites; class F at 30 m
  differs by 24% between the two sets.
- The urban σ_z coefficient for classes E/F was 10× too large.
- `mass_emitted_kg` ignored the factor's mass-unit multiplier while `tCO2e`
  applied it, so the two ledger columns disagreed by 1000× for gram-based
  factors.
- The provenance table declared 7 columns and emitted 6, so the PDF renderer
  silently dropped every row.
- The scenario decomposition used the new quantity in the factor term, which
  double-counted the interaction and did not reconcile.

[Unreleased]: https://github.com/lastnight030506/ghg-inventory-engine/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lastnight030506/ghg-inventory-engine/releases/tag/v1.0.0
