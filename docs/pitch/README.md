# Pitch figures

Eleven 16:9 slides (2000 x 1125 px). Regenerate with `python scripts/pitch_figures.py` and `python scripts/pitch_figures_market.py`. Every number is either
measured by us (`docs/ml_report/metrics.json`) or taken from a cited source, and each slide says which.

| # | Slide | Say this | Evidence |
| --- | --- | --- | --- |
| 1 | `01_problem.png` | India collects 92% of its waste but processes only 54%, and 22% is unmanaged. Chandigarh collects everything, yet the national regulator's figures show about 15% processed and 90% landfilled. | CPCB annual report 2021-22 |
| 2 | `02_loop.png` | One loop from report to verified cleanup. Software suggests at four steps; people decide or act at the other three. | Our design |
| 3 | `03_lifecycle.png` | A report cannot be marked closed by hand. Approval, progress and verification only come from their own flows, and every step is logged. | `civicloop/api.py`, `services/verification.py` |
| 4 | `04_architecture.png` | One role-gated, city-scoped API in front of four small engines that can each be swapped. | Our code |
| 5 | `05_tenancy.png` | Each city is a separate workspace with its own people, data and risk model. A platform admin confirms real cities. | 18 isolation tests |
| 6 | `06_routes.png` | Planned rounds are 8 to 16% shorter than nearest-stop-next, and urgent sites come earlier in the round. | Our measurements, plus two outside studies for context |
| 7 | `07_scorecard.png` | What the models can and cannot do yet, on simulated data only. | `docs/ml_report/metrics.json` |
| 8 | `08_next_steps.png` | What an 8-week pilot would measure to move from simulated to proven. | Proposal |
| 9 | `09_feasibility.png` | Where to sell first: a no-fee city pilot, then contractors and bulk-generator compliance; tenders and consumers last. | Our judgement from `market-and-pricing.md` |
| 10 | `10_pricing.png` | Subscription tiers, and why a Chandigarh-size city breaks even at a 1 to 2% saving. | Estimate with stated assumptions |
| 11 | `11_competitors.png` | Who else is in this space and what each kind does, with an honest read of our gaps. | Public descriptions; `competitors.md` |

## What to be careful about when presenting

- **Slide 1, Chandigarh.** The CPCB table gives 540 t/day generated and collected, 83 t/day processed and 486 t/day landfilled.
  Those last two add up to more than 540, and the report flags the row with a footnote, so quote the shares, not a sum.
  Local reporting disagrees about the city's plant: officials have reported 455 to 490 t/day processed, while independent
  accounts put it nearer 80 to 120 t/day, and a Member of Parliament said the plant had been idle since April 2024.
  If a judge knows Chandigarh well, say "as reported to CPCB in 2021-22" and name the dispute yourself.
- **Slide 6.** Our savings are against a nearest-stop-next rule on random layouts, in straight lines. They are not savings
  against a real fleet on real roads. Other cities report 4.8% (Ghana) and about 8% (Sydney) distance savings from route
  optimisation, so single digits to low double digits is the realistic expectation. Do not quote the 15.7% as a promise.
- **Slide 7.** The risk model is a modest ranker (AUC about 0.65 to 0.67) and beats the hand-set formula clearly in 5 of 10
  simulated cities, not all. Duplicate detection was tested on 40 hand-written pairs. The photo analysis (Gemini) has not
  been measured at all because no labelled photos exist; say so before someone asks.
- **Slide 3.** The after-photo check compares file content, not what the picture shows. An image-based check is a pilot item.

Market research, feasibility ranking and the pricing logic are in `market-and-pricing.md`. Competitors, threat ranking and our product gaps are in `competitors.md`.

## Sources

- CPCB, *Annual Report on Solid Waste Management 2021-22*: https://cpcb.gov.in/uploads/MSW/MSW_AnnualReport_2021-22.pdf
  (national: 1,70,339 t/day generated, 92% collected, 54% processed, 24% landfilled, 22% gap; Chandigarh row in Table 1).
  Read directly from the PDF.
- Chandigarh plant and processing disputes, The Tribune:
  https://www.tribuneindia.com/news/chandigarh/centre-evades-query-on-waste-mgmt-plant-lying-idle-mp and
  https://www.tribuneindia.com/news/chandigarh/swachh-bharat-records-belie-ground-reality-128206/amp
- Ghana route-optimisation study (4.79% less distance, 10.81% less fuel):
  https://pure.ug.edu.gh/en/publications/effect-of-optimal-routing-on-travel-distance-travel-time-and-fuel/
- Sydney fleet routing study (about 8% less distance):
  https://researchers.westernsydney.edu.au/en/publications/vehicle-routing-optimization-for-improving-fleet-fuel-efficiency-/
- The Ghana, Sydney and Tribune figures come from search summaries; I did not open the full papers or articles, so check
  them before quoting a number on stage.
