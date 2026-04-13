# AB Test Results: kanker_nl_drilldown

## Aggregate Metrics

| Variant | Chunks | Avg Words | Recall@5 | Precision@5 | MRR | vs Baseline |
|---------|--------|-----------|----------|-------------|-----|-------------|
| B300_baseline | 5853 | 242.1 | 0.800 | 0.440 | 0.717 | — |
| B150_small | 11252 | 132.1 | 0.767 | 0.500 | 0.686 | -4.2% / +13.6% / -4.3% |
| B200_medium | 8568 | 172.5 | 0.800 | 0.473 | 0.668 | +0.0% / +7.6% / -6.8% |
| B250_large | 6910 | 208.8 | 0.733 | 0.420 | 0.576 | -8.3% / -4.5% / -19.6% |

## Per-Category Breakdown

### Living With

| Variant | Recall@5 | Precision@5 | MRR |
|---------|----------|-------------|-----|
| B300_baseline | 0.700 | 0.340 | 0.450 |
| B150_small | 0.500 | 0.260 | 0.308 |
| B200_medium | 0.500 | 0.280 | 0.350 |
| B250_large | 0.500 | 0.280 | 0.320 |

### Symptom

| Variant | Recall@5 | Precision@5 | MRR |
|---------|----------|-------------|-----|
| B300_baseline | 0.900 | 0.460 | 0.900 |
| B150_small | 0.900 | 0.460 | 0.850 |
| B200_medium | 1.000 | 0.500 | 0.900 |
| B250_large | 0.900 | 0.400 | 0.683 |

### Treatment

| Variant | Recall@5 | Precision@5 | MRR |
|---------|----------|-------------|-----|
| B300_baseline | 0.800 | 0.520 | 0.800 |
| B150_small | 0.900 | 0.780 | 0.900 |
| B200_medium | 0.900 | 0.640 | 0.753 |
| B250_large | 0.800 | 0.580 | 0.725 |

## Decision

**Result: Baseline wins.** No alternative improved on both Recall@5 and MRR.