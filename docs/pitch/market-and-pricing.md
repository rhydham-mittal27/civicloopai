# Market, feasibility and pricing

Research done 23 Oct 2026. Slides: `09_feasibility.png`, `10_pricing.png` (regenerate with `python scripts/pitch_figures_market.py`).

**Read this first.** Where a number is ours (a score, a price, an estimate) it says so. Where it comes from a source, the link is
at the bottom, and I note when I only saw a search summary and not the full document. Several inputs are old, secondhand or from
vendor blogs. The conclusions below hold only as far as those inputs do, and the pricing needs customer interviews before it is
quoted to anyone.

---

## 1. The market

**Overall waste market (big, but not our market).** Published sizes vary a lot by publisher: India solid waste management about
US$12.2 billion in 2024 (IMARC), the wider waste market about US$15.1 billion (MarketsandMarkets), municipal solid waste about
US$7.4 billion (Mordor). None of the summaries I could read gave a size for the **software** slice, so I do not claim one.
A smart-waste growth rate of 16.3% a year for India appears in a Future Market Insights summary, but that is a growth rate inside a
global report, not a market size.

**Demand and money for cities.**
- India generated 1,70,339 tonnes a day in 2021-22; 92% was collected, 54% processed, 24% landfilled and 22% unmanaged
  (CPCB, read from the PDF). Collection is largely solved on paper; processing and the gap are not.
- Central money is shrinking, which is a risk for anything sold to cities. Swachh Bharat Mission (Urban) 2.0 had a 2021-26 outlay of
  about Rs 1,41,600 crore (central share Rs 36,465 crore). The urban allocation was Rs 5,000 crore in 2025-26 and was reported cut to
  Rs 2,500 crore in 2026-27. The Cabinet approval I found runs "till 2025-26"; I did not find what replaces it.
- Cities spend little per tonne. Secondary sources cite Rs 500 to 1,000 a tonne (one says up to 1,500), about 60 to 70% of it on
  collection, and Rs 50 to 250 per person. These trace to a 2013 advisory and a 2017 study, so treat them as old.
- City finances are weak. The RBI's municipal-finance reports describe revenue dominated by property tax and grants, falling capital
  spending, and little financial autonomy.
- Buyers are many and small. About 4,372 urban local bodies (PIB, 2021), of which about 279 are municipal corporations (a list based
  on Census 2011). A national count I could verify did not exist in the results; 4,041 comes from Census 2011.

**What cities already buy.** The large tenders are for GPS tracking hardware plus a platform, not for workflow software. Gujarat's
state-wide RFP for GPS tracking of waste vehicles is listed at Rs 74 crore; Rajasthan's QR-based tracking at Rs 137 crore.
Vendors include NEC India, Convexicon (Varanasi smart city), SafaiMitra, WeVOIS, MapmyIndia and SCS Tech. Platform fees quoted by
vendor blogs run Rs 75 to 400 per vehicle a month (some say Rs 500 to 1,500 including more features), plus Rs 100 to 200 for SIM and
data, hardware separate. **None of these are tender prices**, and I found no published per-vehicle rate in an actual tender.

**The free competitor for citizen reporting.** The government's Swachhata-MoHUA app (built by Janaagraha) already takes garbage
complaints, assigns them to the local engineer and asks for an after-photo before closing. A 2020 official release gave over
1.7 crore users. Reviews complain of complaints marked resolved with unrelated photos. So reporting is a free commodity; the gap is
**checking that the work was really done**, which is the part we built.

**Private buyers.**
- Contractors. Antony Waste Handling Cell earned Rs 580.6 crore from collection and transport in FY25 under municipal contracts
  (company release), including a Rs 908 crore Navi Mumbai renewal. Companies like this run large fleets for cities and carry the
  penalty risk when service slips.
- Bulk waste generators. The Solid Waste Management Rules 2026 took effect on 1 April 2026. Reported thresholds: built-up area over
  20,000 sq m, or water use over 40,000 litres a day, or waste over 100 kg a day. Obligations: registration, segregation into four
  streams, on-site processing or an approved arrangement, audits uploaded to a central portal, and environmental compensation for
  breaches. Most of this came from news and exam-prep summaries, **not the gazette**, so confirm thresholds against the notified text.
  Delhi's MCD already runs a bulk-generator registration platform. One commentary says verifying self-reported data is an open
  question, which is where audit trails fit.
- Adjacent player: Recykal (Hyderabad), well funded, sells EPR compliance software and a marketplace to brands and recyclers, and
  reports 30 municipalities. It is a likely competitor or partner for the compliance segment.

---

## 2. Feasibility ranking (our judgement)

Scored 1 to 10 for the next 12 months. They weigh how easy the buyer is to reach, how fast and reliably they pay, how well the
product fits today, and the size of the ticket.

| Rank | Route to revenue | Score | Why |
| --- | --- | --- | --- |
| 1 | **B2G: no-fee pilot with one city** (MoU) | 8.0 | Easy to start, product is ready, no tender needed. Earns credibility and real data. Earns almost no money. |
| 2 | **B2B: waste contractors** | 6.5 | They bear the penalties, they run the fleets, and they need proof of service to show the city. Private buyers decide faster than cities. Our routes, photo evidence and SLA reports fit. Needs a customer to confirm. |
| 3 | **B2B: bulk-generator compliance** | 6.0 | Rules created demand this year. But we have not built registration, certificates, segregation logs or portal export, so product fit is partial, and Recykal-style players are adjacent. |
| 4 | **B2G: paid city licence, direct purchase** | 4.5 | A city-sized contract is small (about Rs 9 lakh a year). Payment is slow and budgets are shrinking. I did not verify the direct-purchase limits. |
| 5 | **B2G: state tender or smart-city integrator** | 3.0 | Big tenders go to integrators selling GPS hardware. Lowest bid often wins, which punishes a software product. Startup guidance cites 90 to 120 day payment delays. |
| 6 | **B2C: citizens pay** | 1.5 | A free government app already covers reporting. |

**The project itself, as a venture today (our scores):**

| Dimension | Score | Note |
| --- | --- | --- |
| Product readiness | 7 | Four roles, many cities, routes, evidence checks, 75 passing tests. Not yet used by a real city. |
| Evidence it works | 3 | Every model result is simulated or hand-written. Gemini photo analysis is unmeasured. No pilot data. |
| Differentiation | 6 | Verified closure plus routing plus per-city models in one tool. Reporting alone is free. Not defensible against a funded rival yet. |
| Ease of selling | 4 | Small buyers, slow processes, falling central funds. B2B is easier than B2G. |
| Revenue potential | 4 | See the ceiling below: a good niche, not a large market on its own. |
| **Overall** | **about 5 of 10** | A credible pilot-stage product with an honest path. Not yet a proven business. |

**Revenue ceiling (our arithmetic).** If every one of about 4,372 cities bought: 279 corporations at about Rs 9 lakh plus 4,093
others at about Rs 2 lakh is roughly **Rs 107 crore a year**. At 1 to 3% of cities that is **Rs 1 to 3 crore**. An illustrative year
three: 10 cities at Rs 8 lakh, 3 contractors at Rs 30 lakh, 300 bulk sites at Rs 20,000 is about **Rs 2.3 crore**. That supports a
small team, not a large company. Growth would need more products for the same buyers or other countries.

---

## 3. B2B or B2G? Recommendation

**Lead with B2B, use B2G as proof.**
1. Sign one **no-fee city pilot** (Chandigarh is the natural one). Its job is evidence and a reference, not revenue.
2. Sell to **contractors** next. A private buyer pays on a normal timeline and values proof of service. Ask the pilot city to
   introduce the contractor that runs its collection.
3. Build the missing **compliance features** and test **bulk generators** with 10 interviews before investing.
4. Treat **tenders and integrators** as a later channel, through a partner who already sells to cities.
5. Do not build for consumers to pay.

What would change this: a city or state that wants a paid pilot and funds it, a contractor that commits to a paid trial, or a
state mission that adopts the product as its closure-verification layer.

---

## 4. Subscription model and why

Annual, invoiced once a year (matches how cities buy and avoids monthly chasing).

| Plan | Price | Includes | Why this price |
| --- | --- | --- | --- |
| **City pilot** | Rs 0, 90 days | 1 to 2 wards, up to 25 vehicles; credited to year one if the city continues | Removes the buying barrier; produces the evidence |
| **City licence** | **Rs 1 lakh platform + Rs 250 per active vehicle a month**, minimum Rs 2 lakh a year | All roles, AI photo analysis, routes, verification, audit log, per-city risk model | See below |
| **Contractor** | **Rs 400 per vehicle a month**, minimum 25 vehicles | Routes, proof-of-service photos, reports for the paying city | Private buyers pay more than cities and judge it on ROI |
| **Bulk generator** | **Rs 12,000 a site a year** (basic) to **Rs 30,000** (plus) | Registration reminders, segregation logs, audit-ready records, vendor photo proof, portal export | Unvalidated; set against the cost of non-compliance, which I could not price |
| Multi-city or state | Negotiated, suggest 10% off for 3 years, 20% for a state | Shared admin, platform switching | Volume |

**Why Rs 250 a vehicle.** It sits inside the Rs 75 to 400 platform-fee range vendors quote for tracking tools, at the upper half
because we do more than tracking. It is far below Western route software: Samsara-type telematics is about US$27 to 33 per vehicle a
month, Routeware is estimated at US$100,000 to 400,000 a year, and a US city paid about US$204,000 to 246,000 a year for route
software.

**Why it pays for itself (worked example, Chandigarh-size).**
- 540 tonnes a day (CPCB) x 365 x Rs 500 to 1,000 a tonne = **Rs 9.9 to 19.7 crore** a year of collection spending (old benchmark).
- Assume routing can influence half of that, and saves 5%. Studies elsewhere report 4.8% less distance (Ghana) and about 8%
  (Sydney). That is **Rs 25 to 49 lakh** a year.
- 270 collection vehicles (Tribune) x Rs 250 x 12 + Rs 1 lakh = **Rs 9.1 lakh**. That is 18 to 37% of the estimated saving, and it
  **breaks even at a 1 to 2% saving**.
- Weak points: the per-tonne figure is old, "half the spend" is my assumption, and savings from our own tests were against a simple
  rule on random layouts, not against Chandigarh's actual routes. The pilot should measure the real baseline.

**Why Rs 400 for contractors.** Same top-of-range logic, plus private buyers carry service penalties and fuel costs themselves.
I have no data on those penalties. Treat Rs 400 as a starting offer to test, not a conclusion.

**What I could not price.** Our own costs. The AI photo analysis costs per report; I did not verify Gemini's current price, so measure
the cost per report in the pilot before promising "AI included" at scale.

---

## 5. Risks to be honest about

- Central funding for urban sanitation fell, and the mission period I found ended in 2025-26.
- Cities buy slowly and pay late; lowest-bid tenders favour hardware vendors. (Practitioner advice, not measured data.)
- No real data yet: the models and the photo analysis are unproven on real reports.
- Competitors with funding and city relationships exist (Recykal, GPS integrators); the government app is free.
- Compliance rules are new and summarised from secondary sources; thresholds may differ in the notified text.

---

## Sources

Market and policy
- CPCB, Annual Report on Solid Waste Management 2021-22 (read from the PDF): https://cpcb.gov.in/uploads/MSW/MSW_AnnualReport_2021-22.pdf
- IMARC India solid waste management market: https://www.imarcgroup.com/india-solid-waste-management-market
- MarketsandMarkets India waste management: https://www.marketsandmarkets.com/Market-Reports/geography/waste-management-market/india
- Mordor Intelligence India municipal solid waste: https://www.mordorintelligence.com/industry-reports/india-municipal-solid-waste-management-market
- Future Market Insights, smart waste management: https://www.futuremarketinsights.com/reports/smart-waste-management-market
- Cabinet approval of SBM-U 2.0: https://www.pmindia.gov.in/en/news_updates/cabinet-approves-the-continuation-of-swachh-bharat-mission-urban-sbm-u-till-2025-26-for-sustainable-outcomes/
- Budget 2026 cut to Swachh Bharat allocation: https://www.theenvironment.in/2026/02/01/budget-2026-swachh-bharat-allocation-reduces-by-26-per-cent-urban-sanitation-hit-hard/
- RBI report on municipal finances (summaries): https://factly.in/review-rbis-report-on-municipal-finances-highlights-the-inadequate-revenues-of-ulbs/
- NITI Aayog, Waste-Wise Cities: https://www.niti.gov.in/sites/default/files/2021-12/Waste-Wise-Cities.pdf
- PIB, 4,372 urban local bodies: https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1744759&reg=48&lang=2

Competitors and buyers
- Recykal: https://www.indianretailer.com/news/funding-alert-recykal-raises-23-mn-bridge-funding-accelerate-circular-economy-growth
- Convexicon (Varanasi): https://www.convexiconindia.com/solid-waste-management-solutions/
- SafaiMitra: https://www.safaimitra.com/
- NEC India: https://in.nec.com/en_IN/solutions_services/intelligent_transport_solutions/solid_waste_management.html
- Swachhata-MoHUA app (2020 release): https://www.pib.gov.in/PressReleasePage.aspx?PRID=1612458 and reviews https://apps.apple.com/in/app/swachhata-mohua/id1124033628
- Antony Waste FY25 results: https://www.antony-waste.com/docs/investors/financial_reports/PressRelease/2024_25/AWHCLEarningsPressReleaseQ4FY25.pdf
- Gujarat GPS tracking RFP: https://gil.gujarat.gov.in/tendercms/TenderDocs/2026716113924298.pdf
- Chandigarh door-to-door fleet (270 vehicles): https://www.tribuneindia.com/news/chandigarh/relief-for-upper-floor-residents-as-chandigarh-mc-approves-door-to-door-garbage-collection/amp

Rules and procurement
- Solid Waste Management Rules 2026 (summaries): https://www.drishtiias.com/daily-updates/daily-news-analysis/solid-waste-management-swm-rules-2026/print_manually and https://visionias.in/current-affairs/upsc-daily-news-summary/article/2026-01-29/the-indian-express/environment/centre-notifies-new-solid-waste-management-rules-places-larger-onus-on-bulk-generators
- Delhi MCD bulk generator registration: https://www.theweek.in/wire-updates/national/2024/11/24/des29-dl-mcd-waste-management.html
- Selling to government, pricing a tender: https://echai.ventures/startingup/selling-to-government/how-do-i-actually-price-a-bid-so-i-win-the-tender-but-don-t-lose-money-on-the-contract
- L1 critique and reform: https://www.nbmcw.com/news/govt-bidding-adieu-to-l1-tendering-norm.html

Pricing benchmarks (vendor and review sites, not official)
- GPS tracking costs in India: https://www.sahajgps.com/blog/gps-tracker-monthly-subscription-in-india-what-are-you-paying-for/
- Routeware: https://fieldservicesoftware.io/software/routeware/
- Savannah route software contract: https://agenda.savannahga.gov/publishing/april-22-2021-city-council-regular-meeting/265_6245.html
- Samsara pricing estimate: https://tech.co/fleet-management/samsara-fleet-management-review

Route savings elsewhere
- Ghana: https://pure.ug.edu.gh/en/publications/effect-of-optimal-routing-on-travel-distance-travel-time-and-fuel/
- Sydney: https://researchers.westernsydney.edu.au/en/publications/vehicle-routing-optimization-for-improving-fleet-fuel-efficiency-/

For most of these I saw a search summary, not the full page. The CPCB report is the only one I read directly. Check any figure you
plan to quote on stage.
