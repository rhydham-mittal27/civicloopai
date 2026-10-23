# CivicLoop competitors

Research done 23 Oct 2026. Slide: `11_competitors.png`.

**How far to trust this.** I read public pages and search summaries. I did not use any of these products, and I read no full
company filings. Capability claims are mostly vendor marketing. Where I found nothing, that means nothing public, not that the
feature is missing. Funding and revenue figures come from aggregator sites that often disagree; I flag the conflicts.

## The short version

No one competitor does everything CivicLoop does. But **every single feature has a competitor**, and the closest threats are
better funded and already inside cities. Our real position is narrow and defensible only in one place: **checking that a cleanup
actually happened, then using that to prioritise and route the next one.** Everything else (reporting, tracking, routing) is
already sold or given away.

## 1. Government complaint apps (free, and the biggest force)

| Product | What it does | What I found |
| --- | --- | --- |
| **Swachhata-MoHUA** (built by Janaagraha) | Citizens photograph garbage; the complaint goes to the ward's sanitary inspector; the engineer must upload an after-photo; the citizen has 7 days to accept or reject | Over 1.7 crore users in 2020 (official release). Reviews complain of complaints closed with unrelated photos. |
| **Indore 311** | Geotagged photo to the zonal officer, 24-hour target, officer uploads a photo of the cleaned spot | An older independent assessment found 36% of 311 complaints resolved within 24 hours. |
| **Bengaluru Anveshak (pilot)** | A ticket closes only after a photo taken **within 50 m** of the original location | Run with Chitragupta Urban Technologies; the city decides whether to extend it. This is the closest thing to our evidence gate in a government product, and it is a geofence, not an image check. |
| **MCD 311 (Delhi)** | Complaints, bulk-waste-generator registration; a chatbot is proposed | No photo-verification found. |
| **PMC CARE (Pune)** | Photo and location complaints | A third-party guide says complaints are often closed without action and cannot be challenged. Unverified. |

**What this means for us.** Citizen reporting is free and already in 4,900+ towns (a claim from one post; not official). We
cannot sell reporting. But these apps are weak at the part after the report: ranking, routing and **proving** the fix. The risk
is that the ministry or a big city adds stronger verification itself, as Bengaluru has started to. The opportunity is to take
their complaints as an input (we already have a manual import) and sell the layer on top.

## 2. Indian city waste-operations platforms (the most direct commercial rivals)

| Company | Reach and money | What they sell |
| --- | --- | --- |
| **WeVOIS Labs** (Jaipur) | Claims 36+ cities and 7 lakh tonnes managed. Series A of Rs 36 crore in Jan 2025. Revenue Rs 51.1 crore in FY25, up 54% (Inc42). Funding totals conflict between sources ($4.8M vs $10.2M). | RFID collection tracking, route planning, mapping, citizen alerts, dashboards, plus it runs collection operations itself in some cities. |
| **SafaiMitra** | No independent customer count or funding found. | SaaS: GPS tracking, GIS, RFID/QR, complaint management, weighment. Vendor claims 20% less fuel in an unnamed city. |
| **Convexicon, NEC India, SCS Tech, MapmyIndia** | NEC and Convexicon name smart-city projects (Varanasi). | IoT, GPS, RFID, CCTV, GIS for municipal corporations, usually sold through large tenders. |

**Threat.** **WeVOIS is the one to watch.** It is funded, in dozens of cities, can add AI features, and as an operator it sits on
the contract and the data. It could build what we do. Our edge over it would have to be speed on verification and prioritisation
and being software-only, which a city that wants to keep its own contractors might prefer.

**We now match these on basic live GPS tracking** (a crew phone or any tracker can feed us), but not on RFID, weighbridge data or
years of deployed hardware. They own the vehicle data a route optimiser ideally uses, so accepting a feed from the city's existing
tracking vendor is the realistic path.

## 3. Compliance and marketplace

**Recykal** (Hyderabad) sells EPR traceability software and a recycling marketplace to brands, aggregators and recyclers, and says
it works with 30 municipalities. Reported Series B of about $40M (Dec 2024) and a later round; one report gives FY26 gross revenue
of Rs 1,498 crore, which is marketplace turnover, not software revenue. It is the likely leader for the **bulk-generator
compliance** segment I rated 6 of 10 for us. Treat it as both a competitor and a possible partner. Kabadiwalla Connect and
Ishitva serve recycling and sorting, which is adjacent, not head-on.

## 4. Global route, sensor and city-work software

| Company | Note |
| --- | --- |
| **Routeware, Rubicon (RUBICONSmartCity), Samsara** | Mature route and fleet software. Routeware is estimated at $100k to $400k a year; Samsara-type telematics about $27 to 33 per vehicle a month; one US city paid about $204k to $246k a year for route software. Priced for Western budgets, so not natural fits for small Indian cities, but they set the feature bar. |
| **Enevo, Sensoneo, Evreka, Bigbelly** | Fill-level sensors and analytics for bins. Needs hardware we do not have. (One source says Enevo was acquired in 2021, another does not; unresolved.) |
| **CivicPlus SeeClickFix, Cityworks, Lucity** | US 311 and public-works software. Estimates of $2,500 to $50,000 a year for SeeClickFix tiers, quote-only for the others; unverified. They show what a mature product in our category looks like and what cities there pay. |

## 5. AI grievance start-ups

Vendors such as **AI Sahayak** and **Nagrik Dwar** market AI that sorts complaints and compares before and after photos. These are
marketing pages with no independent evaluation. Treat as a claim to test, and note that they confirm buyers want this feature,
which makes "AI before-and-after" less unique over time.

## Threat ranking (our judgement)

1. **WeVOIS Labs.** Funded, in many cities, controls operations data. Highest.
2. **Government apps adding verification** (Bengaluru-style). Free, trusted, and can reach every city. Highest impact if it happens, uncertain timing.
3. **Recykal** in compliance. Strong in that one segment.
4. **SafaiMitra and the GPS integrators.** Win tenders; could add routing and verification.
5. **Global vendors.** Too expensive and hardware-bound for small cities; matter more for large contractors.
6. **AI-grievance start-ups.** Unproven, but copy the same idea.

## Where we are different

| Our edge | How solid it is |
| --- | --- |
| An evidence gate: a report is only verified with a finished job and an after-photo that is not the same file as the before-photo | Built and tested. It checks the file, not what the photo shows, so it is the weakest form of the claim. Bengaluru already enforces location. |
| One loop: report, AI rating, hotspot risk, route, verify, audit | Built. No competitor I found does all of it, but each piece exists elsewhere. |
| Honest evaluation: a model only ships if it beats the formula; results labelled simulated | A real trust advantage in a sector full of marketing claims. Not a moat; it can be copied. |
| Per-city isolation and a platform admin | Built. Expected by buyers, not a differentiator. |
| Software-only, priced for a small city | True, but price is easy to undercut and tracking vendors bundle software for free. |

## Gaps this exposes in our product

- **Live GPS tracking is now built** (phone or tracker feed, live map). Still missing: RFID and weighbridge input, and showing a truck against its planned route, so plans are not yet checked against real trips.
- The after-photo check does not look at the image. A real version (location match, image comparison) is a pilot item.
- No bulk-generator compliance features, where Recykal and the new rules are strong.
- Nothing proven on real data: the model, the AI photo reading and the savings are all simulated or unmeasured.
- No native mobile app or offline mode, which field crews in poor-signal areas may need. (I did not test the web app offline.)

## What to do about it

1. **Pitch us as the layer on top**, not a replacement: it takes complaints from Swachhata or a city's 311 and gives back a ranked, routed, verified job list.
2. **Add location-based closure** (match the after-photo to the report's location, as Bengaluru does) before a pilot. It is cheap and closes the most obvious hole.
3. **Integrate, do not rebuild, tracking.** The tracker endpoint already accepts a feed with a per-vehicle key; add an adapter for the city's existing vendor's format.
4. **Pick one pilot city and measure** real time-to-clear and repeat-site rate. That evidence is the only thing none of the claims above can match.
5. Treat WeVOIS as the benchmark: study its city list and ask pilot cities what it cannot do for them.

## Sources

- Swachhata-MoHUA (2020 release and reviews): https://www.pib.gov.in/PressReleasePage.aspx?PRID=1612458 , https://apps.apple.com/in/app/swachhata-mohua/id1124033628
- Indore 311: https://www.smartcityindore.org/311-app/ , assessment: https://publications.jsi.com/JSIInternet/Inc/Common/_download_pub.cfm?id=23212&lid=3
- Bengaluru AI civic tracking pilot: https://urbanacres.in/bengaluru-deploys-ai-technology-to-track-civic-problems-faster/
- MCD 311 chatbot: https://www.tribuneindia.com/news/delhi/mayor-proposes-chatbot-for-mcd-311-app
- PMC CARE: https://play.google.com/store/apps/details?id=in.gov.pmc.pmccare&hl=en_IN and https://pmc.opinify.co.in/
- WeVOIS: https://inc42.com/company/wevois-labs/ , https://thebetterindia.com/sustainability/wevois-labs-tech-waste-management-india-abhishek-gupta-abhinav-vashistha-workers-12568024 , https://www.marcamoney.com/wevois-raises-36-crore-in-series-a-funding-round-led-by-negen-capital-and-vyom-wealth/
- SafaiMitra: https://www.safaimitra.com/
- Convexicon: https://www.convexiconindia.com/solid-waste-management-solutions/ ; NEC India: https://in.nec.com/en_IN/solutions_services/intelligent_transport_solutions/solid_waste_management.html
- Recykal: https://www.indianretailer.com/news/funding-alert-recykal-raises-23-mn-bridge-funding-accelerate-circular-economy-growth
- Enevo and Sensoneo competitor lists: https://www.cbinsights.com/company/enevo/alternatives-competitors
- Routeware pricing estimate: https://fieldservicesoftware.io/software/routeware/ ; Savannah contract: https://agenda.savannahga.gov/publishing/april-22-2021-city-council-regular-meeting/265_6245.html
- SeeClickFix, Cityworks pricing estimates: https://www.spendbase.co/vendors/civicplus-seeclickfix-311-crm/ , https://www.capterra.com/p/80839/CityWorks/
- AI Sahayak and Nagrik Dwar (vendor pages): https://ai-sahayak.vercel.app/ , https://www.drema.in/portfolio/nagrik-dwar-municipal-grievance-platform
