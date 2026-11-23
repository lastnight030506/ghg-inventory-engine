# GHG Inventory Engine — Handover Report

Automated Scope 1/2/3 GHG inventory and Gaussian plume dispersion engine for an exporting
manufacturer preparing for EU CBAM and ISO 14064-1 reporting.

- **Repository:** https://github.com/lastnight030506/ghg-inventory-engine (public, branch `master`, HEAD `8a88e1b`)
- **Code size:** 2,755 lines across `src/ghg/*.py` and `tests/*.py`
- **History:** 3 commits, tree clean, remote in sync

## What was built

| Component | Location | Purpose |
|---|---|---|
| Activity ingestion | `src/ghg/activity.py` | Loads plant activity data from `data/activity/` |
| Factor register | `src/ghg/factors.py`, `data/factors/emission_factors.csv` | Validation + lookup of emission factors |
| Inventory engine | `src/ghg/inventory.py` | Scope 1/2/3 roll-up, ledger with per-gas and tCO2e columns |
| Dispersion | `src/ghg/dispersion.py` | Gaussian plume, Pasquill-Gifford, plume rise, downwash |
| Plume map | `src/ghg/plume_map.py` | Vectorised numpy downwind contour footprint |
| Charts | `src/ghg/chart.py` | Monthly trend and scope breakdown PNGs (the footprint map is drawn in `plume_map.py`) |
| Report / PDF | `src/ghg/report.py`, `src/ghg/pdf.py` | Markdown + A4 PDF emissions summary |
| CLI | `src/ghg/cli.py` | Single entry point |
| Packaging | `Dockerfile`, `pyproject.toml` | Reproducible build and run |

Inputs under `data/` (activity data, factor register, `stack.json`); sample outputs in `out/`.

**Headline result, 2025: 3,737.05 tCO2e** — Scope 1 1,360.01 (36.4%), Scope 2 2,138.23 (57.2%),
Scope 3 238.81 (6.4%). Scope 2 dominates and is the obvious target for whoever maintains this.

**Dispersion result:** peak ground-level concentration 340.2 µg/m³ at 811 m downwind
(30 m stack, 25 g/s release, 3 m/s wind, stability D, 800 m mixing height).

**Factor register:** 9 factors across 5 sources, each carrying a citation and publication year.

## Verification

Every command below was run and exited 0.

| Check | Result |
|---|---|
| `pytest tests/` (host, Python 3.12) | 86 passed in 5.53s |
| `ruff check src/ tests/` | All checks passed |
| `docker build -t ghg-verify .` | success, `sha256:853bce84…` |
| `docker run --rm ghg-verify pytest -q` | 86 passed in 6.53s |
| Bind-mounted run as host UID/GID into `/tmp/verify-out` | exit 0, 5 artifacts, host-user-owned |

Artifacts: `emissions_report.md` (16,639 B), `emissions_report.pdf` (200,374 B, 10 pages A4),
`monthly_trend.png`, `plume_footprint.png`, `scope_breakdown.png`. The UID/GID run is the one that
matters: it proves the container writes into a mounted host directory without leaving root-owned files.

## Design decisions and their reasons

1. **Factors live in a CSV register, not in code.** An auditor can read them beside the report.
   The loader rejects any factor lacking a citation, publication year, known gas, or valid mass
   unit, and rejects duplicate `(source, gas)` keys. No factor enters a total without provenance.
2. **IPCC 2006 Table 2.3 (manufacturing/construction), not Table 2.2 (energy industries).**
   A factory furnace is not a power station. Diesel CH4 is 10 kg/TJ vs 3; coal CH4 is 10 vs 1.
   Using Table 2.2 would have understated combustion methane.
3. **Combustion methane is classified `CH4_non_fossil` (GWP 27.0)** per GHG Protocol GWP guidance.
   Fossil CH4 (29.8) is reserved for fugitive sources. There is deliberately no generic `CH4` key,
   so a contributor cannot pick the wrong GWP by default.
4. **Vietnam grid factor 0.6187 tCO2/MWh, data year 2024** (latest official, announced
   30 Sep 2026). The series 0.9130 (2018) → 0.6766 (2022) → 0.6592 (2023) → 0.6187 (2024) is
   pinned by a test, which turns a future data edit into a visible failure.
5. **Dispersion stack:** Gaussian plume with Pasquill-Gifford classes, Briggs rural and urban
   coefficients, Holland plume rise, Briggs stack-tip downwash, ground and mixing-lid reflection
   via an image series, and a uniform-mixing limit when σz > 1.6·L.
6. **Physics constants were checked against published sources rather than recalled**, each pinned
   by a test whose docstring shows the hand arithmetic — the convention to keep when editing one.

## Bugs found and fixed

All five produced plausible output; none crashed. The first two were caught by an independent
physics review **after** the suite was already green — green does not mean correct when no test
asserts the physics.

| Bug | Effect | Fix |
|---|---|---|
| Stack-tip downwash backwards | Raised stack height for slow exit velocity; non-conservative | Lower by 2[(vs/u)−1.5]d |
| Urban wind exponents on rural sites | Class F at 30 m differed by 24% | Pick exponent set by site character |
| Urban σz for E/F 10× too large | 0.0015 vs 0.00015 | Corrected coefficient |
| `mass_emitted_kg` ignored mass-unit multiplier | 1000× disagreement with `tCO2e` for gram factors | Apply multiplier to both columns |
| Provenance table declared 7 columns, emitted 6 | PDF silently dropped every row | Column count matched |

## What a reader must not assume

- **Gaussian plume is a screening model.** Steady wind, flat terrain, no chemistry, no deposition,
  no building downwash. It is not a substitute for AERMOD/ADMS or an EIA.
- **Scope 2 is location-based only.** A market-based figure needs contractual instruments and is a
  separate methodology.
- **Freight factors are tank-to-wheel only.** Well-to-wheel would roughly double them.
- **Activity data is simulated.** Shaped like a real plant, but not anyone's actual meters.
- **This is not an assurance opinion or a compliance determination.**
- Pasquill intermediate cells (A-B, B-C, C-D) are rounded to the more unstable class; documented
  as a `shortcut:` comment.
- The Vietnam 2024 grid factor's letter number is reported inconsistently by secondary sources
  (1232/BNNMT-BĐKH vs 11232/BNNMT-BĐKH). The value 0.6187 and its date agree across four sources;
  cite the value, not the letter number, without checking the primary document.

## Where to start maintaining

`src/ghg/factors.py` and the CSV register carry the domain risk; `src/ghg/dispersion.py` carries
the physics risk. Everything else is plumbing. Changing a coefficient means updating its source
citation and the hand-arithmetic test docstring in the same commit.

---

*Evidence currency: every command in the verification table was executed in this session at the
stated revision, and the PDF layout was inspected page by page. Re-verify against a fresh clone
before relying on the figures after any change to the factor register or the dispersion module.*
