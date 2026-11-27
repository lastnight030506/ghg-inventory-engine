# GHG Inventory Engine — Handover Report

Automated Scope 1/2/3 GHG inventory and Gaussian plume dispersion engine for an exporting manufacturer
preparing for EU CBAM and ISO 14064-1 reporting.

- **Repository:** https://github.com/lastnight030506/ghg-inventory-engine (public, `master`, HEAD `847ed6d`)
- **Code size:** 3,946 lines — `src/ghg/*.py` 2,342 (14 modules), `tests/*.py` 1,604 (11 files)
- **History:** 11 commits, tree clean, in sync

## What was built

| Component | File | Purpose |
|---|---|---|
| Activity ingestion | `activity.py` | Plant data |
| CSV reading | `_csv.py` | Shared header/row checks |
| Data resolution | `paths.py` | `$GHG_DATA_DIR` → `./data` → packaged |
| Clock | `clock.py` | Pinned timestamp |
| Factor register | `factors.py`, `data/factors/*.csv` | Validation, lookup |
| Inventory engine | `inventory.py` | Scope 1/2/3 roll-up |
| Dispersion | `dispersion.py` | Gaussian plume, downwash |
| Plume map | `plume_map.py` | Contour footprint |
| Charts | `chart.py` | Trend and scope PNGs |
| Report / PDF | `report.py`, `pdf.py` | Markdown + A4 PDF |
| Scenario | `scenario.py` | YoY decomposition, both Scope 2 methods |
| CLI | `cli.py`, `__main__.py` | `ghg`, `python -m ghg` |
| Packaging / CI | `pyproject.toml`, `Dockerfile`, `Makefile`, `ci.yml` | Wheel, image, four-job CI |

Files under `src/ghg/`; inputs `data/`; reports in `out/`. `pyproject.toml` forces `data` into the
wheel at `ghg/data/`, so an installed package needs no checkout.

**Headline, 2025: 3,737.05 tCO2e** — Scope 1 1,360.01 (36.4%), Scope 2 2,138.23 (57.2%), Scope 3
238.81 (6.4%). Scope 2 dominates and is the obvious reduction target.

**Dispersion:** peak 340.2 µg/m³ at 811 m downwind (30 m stack, 25 g/s, 3 m/s wind, stability D,
800 m mixing height).

**Scenario, 2024 → 2025:** grid electricity rose 18.24 tCO2e despite a cleaner grid — activity
+158.21 t, factor −130.25 t, interaction −9.72 t. Consumption rose 7.5%, the factor fell 6.1%
(0.6592 → 0.6187). A totals-only report reads "+0.9%", hiding two opposite moves an order of magnitude
larger.

**Factor register:** 9 factors across 5 sources, each cited. The 2024 register uses the 2023 grid
factor (0.6592), the latest published when that inventory was prepared.

## Verification

Every command below was run and exited 0.

| Check | Result |
|---|---|
| `pytest tests/` (host, Python 3.12) | 130 passed in 7.76s |
| `--cov=ghg --cov-fail-under=90` | 96.42% (1146 stmts, 41 missed) |
| `ruff check src/ tests/` | All checks passed |
| `mypy src/ghg` | clean, 14 files |
| `docker build` + in-image `pytest` | 130 passed |
| Bind-mount run as host UID/GID | exit 0, 6 artifacts, host-owned |
| Wheel in a clean venv, CLI with no `data/` | data at `site-packages/ghg/data/` |
| Actions run 45924436624 (`847ed6d`) | four jobs, success in 49s |

`test` runs lint, mypy, the coverage gate and both CLIs; `docker` repeats them in the image;
`installed-package` runs the wheel with no `data/`; `report-is-current` diffs reports against `out/`.

## Design decisions and their reasons

1. **Factors live in a CSV register, not in code.** An auditor reads them beside the report; the loader
   rejects a factor lacking a citation, year, gas or mass unit, and duplicate keys.
2. **IPCC 2006 Table 2.3 (manufacturing), not 2.2 (energy).** A furnace is not a power station: diesel
   CH4 is 10 kg/TJ vs 3, coal 10 vs 1.
3. **Combustion methane is `CH4_non_fossil` (GWP 27.0)** per GHG Protocol guidance; fossil CH4 (29.8)
   is for fugitive sources, and no generic `CH4` key exists to default to.
4. **Vietnam grid factor 0.6187 tCO2/MWh, data year 2024** (announced 30 Sep 2026). The series
   0.9130 (2018) → 0.6766 (2022) → 0.6592 (2023) → 0.6187 (2024) is pinned by a test.
5. **Dispersion:** Gaussian plume, Pasquill-Gifford classes, Briggs coefficients, Holland rise,
   stack-tip downwash, ground and lid reflection, uniform mixing past σz 1.6·L.
6. **Physics constants were checked against published sources**, each pinned by a test docstring.
7. **Scenario changes are decomposed, never just differenced.** `decompose()` splits each source into
   `activity = (Q_new − Q_old)·EF_old`, `factor = Q_old·(EF_new − EF_old)` and
   `interaction = (Q_new − Q_old)·(EF_new − EF_old)`, summing exactly to the observed change, asserted.
   The factor term must use the **old** quantity; the new one double-counts.
8. **Scope 2 is shown both ways and never summed.** Instruments cannot exceed consumption and must be
   named; with none, the output says the market figure is not a reduction.

## Bugs found and fixed

Six defects in round one, seven since. The first six produced plausible output and none crashed; a
physics review found them **after** the suite was green — green is not correct if no test asserts the
physics. The rest came from running the tool against inputs and environments it had never seen; three
were invisible because each check ran from the checkout with the right extras.

| Bug | Effect | Fix |
|---|---|---|
| Stack-tip downwash backwards | Raised stack height | Lower by 2[(vs/u)−1.5]d |
| Urban wind exponents on rural sites | Class F at 30 m off 24% | Exponent by site |
| Urban σz for E/F 10× too large | 0.0015 vs 0.00015 | Corrected |
| `mass_emitted_kg` ignored unit multiplier | 1000× off for grams | Applied to both |
| Provenance: 7 columns, 6 emitted | PDF dropped every row | Aligned |
| Factor effect used new quantity | Interaction double-counted | Use `Q_old`; 200-case random test |
| Default paths CWD-relative | Installed `ghg`: register not found | `paths.py`; data in wheel |
| Ragged row (unclosed quote) | `AttributeError: … strip` | `_csv.py` pads rows |
| Header ` site ` with spaces | Missing column | Names stripped |
| Duplicated column name | Last value won silently | Rejected as ambiguous |
| Factor `scope` of `' 1 '` | Worked by `int()` luck | Strip, then parse |
| `plume.stack` on possibly-`None` state | Latent crash; mypy caught it | Guard the `None` branch |
| Image had bare `pytest`, not `.[dev]` | `pypdf` test turned CI red | Install `.[dev]`; `importorskip` |

## What a reader must not assume

- **The PDF is not byte-identical across systems, and cannot be.** It embeds a subset of the system
  DejaVu font, and distributions ship different builds — verified: host `6d5eb3d5…` vs container
  `94d8e219…`, ~5.7 KB larger in the image. Markdown and PNGs are byte-identical everywhere; the PDF
  only on one system. Text and page count match everywhere, so CI compares Markdown bytes and PDF
  text/pages; a byte comparison would fail on every dependency bump.
- **`SOURCE_DATE_EPOCH` must be set for diffable output.** Otherwise the report stamps the wall clock,
  no two runs agree, and nothing can be verified. CI pins it for every job.
- **Gaussian plume is a screening model.** Steady wind, flat terrain, no chemistry, no deposition, no
  building downwash; not an AERMOD/ADMS or EIA substitute.
- **The headline total is location-based.** Market-based needs contractual instruments and is separate
  methodology; never substituted into or summed with the location-based number.
- **The 2024 scenario uses the grid factor in force at the time, not a restatement** — 0.6592 is what a
  reporter had, not a retrospective adjustment.
- **Freight factors are tank-to-wheel only.** Well-to-wheel roughly doubles them.
- **Activity data is simulated**, shaped like a real plant but not anyone's meters.
- **This is not an assurance opinion or a compliance determination.**
- Pasquill intermediate cells (A-B, B-C, C-D) round to the more unstable class; a `shortcut:` comment.
- The Vietnam 2024 grid factor's letter number is disputed in secondary sources
  (1232 vs 11232/BNNMT-BĐKH); value and date agree across four, so cite the value.

## Where to start maintaining

`src/ghg/factors.py` and the register carry the domain risk, `src/ghg/dispersion.py` the physics risk,
`src/ghg/scenario.py` the decomposition arithmetic. Changing a coefficient means updating its citation
and hand-arithmetic docstring in the same commit.

---

*Every command above was run at the stated revision and the PDF inspected page by page. Re-verify from
a fresh clone after any change to factors, decomposition or dispersion.*
