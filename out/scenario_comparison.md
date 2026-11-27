# Scenario Comparison — VSIP-II plant

**2024 → 2025**  
**Total change:** +139.96 tCO₂e (+3.9%)  
**Generated:** 2025-12-01 00:00 UTC by `ghg-inventory-engine`

A total that fell is not automatically a reduction. Part of any year-on-year change comes from the emission factor being republished, not from anything the plant did. The decomposition below separates the two.

## 1. Headline

| Metric | 2024 | 2025 | Change |
|---|---:|---:|---:|
| Total | 3,597.08 | 3,737.05 | +139.96 |
| Scope 1 | 1,255.61 | 1,360.01 | +104.40 |
| Scope 2 | 2,119.99 | 2,138.23 | +18.24 |
| Scope 3 | 221.49 | 238.81 | +17.32 |

## 2. Why it moved: activity vs factor

The change in each source is split into three terms that sum exactly to the observed difference:

```
activity_effect = (Q_new - Q_old) x EF_old      what the plant consumed
factor_effect   = Q_old x (EF_new - EF_old)      what the factor register said
interaction     = (Q_new - Q_old) x (EF_new - EF_old)
```

| Source | Activity | Factor | Interaction | Sum | Driver |
|---|---:|---:|---:|---:|---|
| `coal_boiler` | +88.25 | +0.00 | +0.00 | +88.25 | activity |
| `diesel_furnace` | +16.15 | +0.00 | +0.00 | +16.15 | activity |
| `grid_electricity` | +158.21 | -130.25 | -9.72 | +18.24 | activity |
| `inbound_freight_road` | +8.82 | +0.00 | +0.00 | +8.82 | activity |
| `inbound_freight_sea` | +8.50 | +0.00 | +0.00 | +8.50 | activity |

## 3. Scope 2: location-based and market-based

The GHG Protocol Scope 2 Guidance requires both figures where contractual instruments exist. They answer different questions and **must not be summed or used interchangeably**.

| Method | tCO₂e | What it measures |
|---|---:|---|
| Location-based | 2,138.23 | average intensity of the grid the plant draws from |
| Market-based | 2,138.23 | the contracts the plant holds, plus residual grid for the rest |

*No contractual instruments: market-based Scope 2 equals the residual factor and is not a reduction against location-based.*

## 4. What this comparison does not tell you

- **Neither total is restated.** A factor change is shown as a factor effect; nothing is rebased.
- **Scope 3 covers inbound freight only** (category 4). Business travel and purchased goods are absent, so the total understates the value chain.
- **The dispersion model is unaffected by year.** It screens one stack under one meteorology; a second year needs its own `data/stack.json`.

**Not a compliance determination.** A verifier will also ask for the boundary declaration, the production-volume denominator, and the evidence behind each contractual instrument.

