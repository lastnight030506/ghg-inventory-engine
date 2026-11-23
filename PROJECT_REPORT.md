# GHG Inventory Engine — Handover Report

Automated Scope 1/2/3 GHG inventory and Gaussian plume dispersion engine for an exporting
manufacturer preparing for EU CBAM and ISO 14064-1 reporting.

- **Repository:** https://github.com/lastnight030506/ghg-inventory-engine (public, `master`, HEAD `57ffa22`)
- **Code size:** 3,430 lines across `src/ghg/*.py` and `tests/*.py`
- **History:** 6 commits, tree clean, in sync

## What was built

| Component | Location | Purpose |
|---|---|---|
| Activity ingestion | `src/ghg/activity.py` | Loads plant activity data |
| Factor register | `src/ghg/factors.py`, `data/factors/*.csv` | Validation + factor lookup |
| Inventory engine | `src/ghg/inventory.py` | Scope 1/2/3 roll-up ledger |
| Dispersion | `src/ghg/dispersion.py` | Gaussian plume, Pasquill-Gifford, downwash |
| Plume map | `src/ghg/plume_map.py` | Vectorised contour footprint |
| Charts | `src/ghg/chart.py` | Trend and scope PNGs |
| Report / PDF | `src/ghg/report.py`, `src/ghg/pdf.py` | Markdown + A4 PDF |
| Scenario | `src/ghg/scenario.py` | YoY decomposition; both Scope 2 methods |
| CLI | `src/ghg/cli.py` | `ghg run`, `ghg scenario` |
| Packaging / CI | `Dockerfile`, `pyproject.toml`, `.github/workflows/ci.yml` | Build, three-job CI |

Inputs under `data/` (2024/2025 activity data, factor registers, `stack.json`); outputs and
`scenario_comparison.md` in `out/`.

**Headline result, 2025: 3,737.05 tCO2e** — Scope 1 1,360.01 (36.4%), Scope 2 2,138.23 (57.2%),
Scope 3 238.81 (6.4%). Scope 2 dominates and is the obvious target for whoever maintains this.

**Dispersion result:** peak ground-level concentration 340.2 µg/m³ at 811 m downwind
(30 m stack, 25 g/s release, 3 m/s wind, stability D, 800 m mixing height).

**Scenario result, 2024 → 2025:** grid electricity rose 18.24 tCO2e despite a cleaner grid — activity
+158.21 t, factor −130.25 t, interaction −9.72 t. Consumption rose 7.5%, the grid factor fell 6.1%
(0.6592 → 0.6187). A totals-only report reads "+0.9%", hiding two opposite moves an order of magnitude
larger.

**Factor register:** 9 factors across 5 sources, each cited. The 2024 register uses the 2023 grid factor
(0.6592), the latest published when that inventory was prepared.

## Verification

Every command below was run and exited 0.

| Check | Result |
|---|---|
| `pytest tests/` (host, Python 3.12) | 102 passed in 5.56s |
| `pytest --cov=ghg --cov-fail-under=90` | 96.15% (1066 stmts, 41 missed); chart 100, inventory/pdf/plume_map/scenario 98, cli 97, activity/report 96, dispersion 93, factors 88 |
| `ruff check src/ tests/` | All checks passed |
| `docker build` + `docker run … pytest` | image `73713cc8…`, 102 passed in 6.48s |
| Bind-mounted run as host UID/GID | exit 0, 6 artifacts (report md+pdf, 3 PNGs, scenario md), host-user-owned |
| GitHub Actions run 45129934025 | three jobs, success in 41s |

CI's `test` job adds `ghg inventory` (reports exist, PDF starts `%PDF`) and `ghg scenario`; `docker`
repeats both; `report-is-current` diffs the regenerated total against `out/emissions_report.md`.

Artifacts: `emissions_report.md`, `emissions_report.pdf` (10 A4 pages), three PNGs, `scenario_comparison.md`.

## Design decisions and their reasons

1. **Factors live in a CSV register, not in code.** An auditor reads them beside the report; the loader
   rejects a factor lacking a citation, year, gas or mass unit, and duplicate keys.
2. **IPCC 2006 Table 2.3 (manufacturing/construction), not Table 2.2 (energy).** A furnace is not a
   power station: diesel CH4 is 10 kg/TJ vs 3, coal 10 vs 1.
3. **Combustion methane is `CH4_non_fossil` (GWP 27.0)** per GHG Protocol guidance; fossil CH4 (29.8)
   is reserved for fugitive sources, and no generic `CH4` key exists to default to.
4. **Vietnam grid factor 0.6187 tCO2/MWh, data year 2024** (announced 30 Sep 2026). The series
   0.9130 (2018) → 0.6766 (2022) → 0.6592 (2023) → 0.6187 (2024) is pinned by a test.
5. **Dispersion stack:** Gaussian plume with Pasquill-Gifford classes, Briggs rural/urban coefficients,
   Holland rise, stack-tip downwash, ground and lid reflection, uniform mixing past σz 1.6·L.
6. **Physics constants were checked against published sources**, each pinned by a test docstring.
7. **Scenario changes are decomposed, never just differenced.** `decompose()` splits each source into
   `activity_effect = (Q_new − Q_old)·EF_old`, `factor_effect = Q_old·(EF_new − EF_old)` and
   `interaction = (Q_new − Q_old)·(EF_new − EF_old)`, summing exactly to the observed change, asserted.
   The factor effect must use the **old** quantity; the new one double-counts.
8. **Scope 2 is shown both ways and never summed.** `Scope2Dual` sets location-based beside
   market-based. Instruments cannot cover more electricity than consumed and must be named; with none,
   the output says the market figure is not a reduction.

## Bugs found and fixed

All six produced plausible output; none crashed. The first two came from an independent physics review
**after** the suite was green — green does not mean correct if no test asserts the physics.

| Bug | Effect | Fix |
|---|---|---|
| Stack-tip downwash backwards | Raised stack height at low exit velocity; non-conservative | Lower by 2[(vs/u)−1.5]d |
| Urban wind exponents on rural sites | Class F at 30 m differed by 24% | Exponent by site |
| Urban σz for E/F 10× too large | 0.0015 vs 0.00015 | Corrected |
| `mass_emitted_kg` ignored mass-unit multiplier | 1000× off `tCO2e` for gram factors | Applied to both |
| Provenance table declared 7 columns, emitted 6 | PDF dropped every row | Aligned |
| Factor effect used the new quantity | Double-counted the interaction; parts stopped reconciling | Use `Q_old`; 200-case randomised test |

The last was found while building the scenario, not by review. Two test expectations also omitted the
kg→tonne ÷1000 step; the code was right, the docstrings wrong.

## What a reader must not assume

- **Gaussian plume is a screening model.** Steady wind, flat terrain, no chemistry, no deposition, no
  building downwash; not an AERMOD/ADMS or EIA substitute.
- **Scope 2 is shown two ways, but the headline total is location-based.** Market-based needs
  contractual instruments and is separate methodology; it sits beside the location-based number, never
  substituted into or summed with it.
- **The 2024 scenario uses the grid factor in force at the time, not a restatement** — 0.6592 is what a
  reporter had, not a retrospective adjustment.
- **Freight factors are tank-to-wheel only.** Well-to-wheel roughly doubles them.
- **Activity data is simulated.** Shaped like a real plant, not anyone's meters.
- **This is not an assurance opinion or a compliance determination.**
- Pasquill intermediate cells (A-B, B-C, C-D) round to the more unstable class; a `shortcut:` comment.
- The Vietnam 2024 grid factor's letter number is reported inconsistently by secondary sources
  (1232 vs 11232/BNNMT-BĐKH). The value 0.6187 and date agree across four sources; cite the value, not
  the letter, without the primary document.

## Where to start maintaining

`src/ghg/factors.py` and the CSV register carry the domain risk, `src/ghg/dispersion.py` the physics
risk, `src/ghg/scenario.py` the decomposition arithmetic. Everything else is plumbing. Changing a
coefficient means updating its citation and hand-arithmetic docstring in the same commit.

---

*Every command above was run at the stated revision and the PDF inspected page by page. Re-verify from
a fresh clone after any change to factors, decomposition or dispersion.*
