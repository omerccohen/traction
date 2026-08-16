# Sector-label audit — revenue evidence, not classification lists

**Date:** 2026-08-13 · **Auditor:** automated pass over SEC XBRL filings · **Deliverable:** report only — `data_cache/universe/broad_sectors.csv` was NOT modified.

## What was tested and how

The labels in `data_cache/universe/broad_sectors.csv` derive from SIC codes assigned at first registration. Cross-checking them against any other classification source is worthless: the SEC's own `sicDescription` is byte-identical to ours for the known-bad cases (CLF: both "Metal Mining"; SEI: both "Oil & Gas Field Machinery & Equipment"; ALOY/DC/NB/CRML/USAR/GMTL: all "Metal Mining"; PLPC: both "Water, Sewer, Pipeline, Comm & Power Line Construction"). **The only test used here is: what does the company actually earn money from, per its own most recent filing.**

Evidence path for every name: SEC `submissions` API → most recent 10-Q / 10-K / 20-F / 40-F → that filing's `FilingSummary.xml` → the rendered XBRL report ("R-file") for *Segment Reporting* / *Disaggregation of Revenue* → segment and product revenue lines. Where a filer publishes no segment R-file (foreign private issuers), the SEC `companyfacts` API or the 6-K financial exhibit was used. All numbers below are read off those filings; no number is inferred. Network access to `sec.gov` / `data.sec.gov` worked throughout — no request failures to report.

**Scope.** 117 companies, being the names actually ranked or named in the live briefings — `rank_thesis1_oilfield_2026-08-11.md` (12), `rank_thesis2_utilities_2026-08-11.md` (36) plus FISN and FRVO named in `target_groups_2026-08-11.md`, `rank_thesis3_grocery_2026-08-11.md` (9), `rank_thesis4_metals_2026-08-12.md` (22), `rank_thesis5_steel_2026-08-12.md` (18), `rank_thesis1_construction_2026-08-07.md` (10), `rank_thesis3_bdc_2026-08-07.md` (8). Not the 2,990-name universe.

**Calibration set re-checked in today's CSV — all six still carry the wrong label:** CLF `Basic Materials / Metal Mining`; ALOY `Basic Materials / Metal Mining`; ARKO `Consumer Staples / Food Chains`; TWI `Industrials / Steel/Iron Ore`; SEI `Consumer Discretionary / Oil and Gas Field Machinery`; GFUZ `Utilities / Electric Utilities: Central`. None has been corrected.

---

## Confirmed wrong

Majority (or entirety) of revenue comes from a business plainly different from the label. Q2 2026 = quarter ended 30 Jun 2026 unless noted.

### A. Operating businesses in the wrong bucket

| Ticker | Current label (Sector / Sub-Industry) | What it actually does | Revenue evidence | Suggested label |
|---|---|---|---|---|
| **SEI** | Consumer Discretionary / Oil and Gas Field Machinery | Mobile gas turbines + behind-the-meter power for data centres | Solaris **Power Solutions $158.3M of $219.4M total = 72.2%** of Q2-26 revenue; Logistics $61.1M (27.8%). Power segment adj. EBITDA $96.4M of $121.2M = 79.5% ([10-Q 2026-08-06](https://www.sec.gov/Archives/edgar/data/1697500/000162828026054349/sei-20260630.htm), *Business Segments — Financial Information by Business Segment*) | Power Generation / Independent Power |
| **DNOW** | Consumer Discretionary / Oil and Gas Field Machinery | Distributor of pipe, valves, fittings and MRO to energy + industrial end markets; manufactures nothing | Q2-26 revenue $1,307M split **Upstream $508M (38.9%)**, Gas Utilities $310M (23.7%), Midstream $272M (20.8%), Downstream & Industrial $217M (16.6%) — **61% is not upstream oilfield** ([10-Q 2026-08-06](https://www.sec.gov/Archives/edgar/data/1599617/000119312526338381/dnow-20260630.htm), *Revenue — Disaggregated by Revenue Source*) | Wholesale Distributors — Industrial/Energy |
| **ARKO** | Consumer Staples / Food Chains | Convenience stores + wholesale fuel distribution | **Fuel revenue $1,965.9M of $2,346.5M = 83.8%**; merchandise $347.4M = 14.8%. Segments: Retail $1,227.3M, Wholesale (fuel) ~$1,097M ([10-Q 2026-08-07](https://www.sec.gov/Archives/edgar/data/1823794/000119312526339096/arko-20260630.htm), *Statements of Operations* + *Reportable Segments*) | Convenience Stores / Fuel Retail |
| **YSWY** | Consumer Staples / Food Chains | Yesway / Allsup's convenience stores — same business as ARKO | **Fuel sales $673.1M of $920.8M = 73.1%**; inside merchandise $240.1M = 26.1%; other $7.5M ([10-Q 2026-08-13](https://www.sec.gov/Archives/edgar/data/1859836/000110465926095497/tmb-20260630x10q.htm), *Segment reporting*) | Convenience Stores / Fuel Retail |
| **CLF** | Basic Materials / Metal Mining | Integrated steel producer | **Steelmaking $5,096M of $5,226M = 97.5%** of Q2-26 revenue; Other Businesses $177M. Steelmaking assets $19,525M of $20,115M ([10-Q 2026-07-23](https://www.sec.gov/Archives/edgar/data/764065/000076406526000100/clf-20260630.htm), *Revenues by Market* + *Assets by Segment*) | Steel |
| **ALOY** | Basic Materials / Metal Mining | REalloys — development-stage rare-earth alloys inside the former Blackboxstocks shell; still books software development cost | Q1-26 **net revenue $706K**, cost of sales $299K, **software development costs $34K**, net loss $(106.7)M; one reportable segment; no mining revenue line exists ([10-Q 2026-05-20](https://www.sec.gov/Archives/edgar/data/1567900/000162828026036966/aloy-20260331.htm), *Statements of Operations*) | Development-stage / Specialty Materials |
| **IE** | Basic Materials / Metal Mining | Ivanhoe Electric — mineral exploration; the only revenue is geophysical data-processing software | Q2-26 revenue **$724K, 100% "Data processing services"**; Santa Cruz Copper, Critical Metals and Energy Storage segments each report revenue **$0**; exploration expense $21.4M ([10-Q 2026-08-07](https://www.sec.gov/Archives/edgar/data/1879016/000187901626000017/ie-20260630.htm), *Revenue (Details)* + *Segment reporting*) | Exploration / Data Services |
| **TWI** | Industrials / Steel/Iron Ore | Titan International — off-highway wheels and tyres | Q2-26 net sales $484.8M; **"Wheels and Tires (incl. assemblies)" $366.3M = 75.6%**; markets are Agriculture $183.6M, Earthmoving/Construction $154.5M, Consumer $146.6M — remainder is undercarriage systems ([10-Q 2026-07-30](https://www.sec.gov/Archives/edgar/data/899751/000089975126000063/twi-20260630.htm), *Segment Information*) | Auto/Industrial Components — Tyres |
| **ATI** | Industrials / Steel/Iron Ore | Nickel-alloy, titanium and zirconium mill products for jet engines | Q2-26 revenue $1,261.1M: **nickel-based & specialty alloys 51%, precision forgings/castings 18%, titanium 15%, zirconium 11%**, precision rolled strip 5% — **~77% is non-ferrous**. End market **Aerospace & Defense 51%** of revenue ([10-Q 2026-08-06](https://www.sec.gov/Archives/edgar/data/1018963/000162828026054233/ati-20260628.htm), *Disaggregation of Revenue*) | Specialty Metals / Aerospace Materials |
| **SXC** | Industrials / Steel/Iron Ore | SunCoke — metallurgical coke producer + industrial material-handling services. Produces no steel and mines no ore | Q2-26 revenue $475.3M: **Domestic Coke $367.5M = 77.3%**, Industrial Services $98.4M = 20.7% (Brazil coke in Corporate) ([10-Q 2026-07-30](https://www.sec.gov/Archives/edgar/data/1514705/000151470526000034/sxc-20260630.htm), *Business Segment Information*) | Coke / Coal Products |
| **ROCK** | Industrials / Steel/Iron Ore | Gibraltar Industries — residential building products (roofing accessories, mail/package, Agtech greenhouses) | Q2-26 net sales $509.5M: **Residential $425.9M = 83.6%**, Agtech $58.8M = 11.5%, Infrastructure $24.9M = 4.9% ([10-Q 2026-08-05](https://www.sec.gov/Archives/edgar/data/912562/000091256226000147/rock-20260630.htm), *Disaggregation of Revenue*) | Building Products |
| **WOR** | Industrials / Steel/Iron Ore | Worthington Enterprises — consumer and building products (post-2023 separation of the steel-processing arm into WS) | FY2026 (yr to 31 May 2026) net sales $1,381.3M; product concentration **Building Products 62%, Consumer Products 38%** ([10-K 2026-07-30](https://www.sec.gov/Archives/edgar/data/108516/000119312526325872/wor-20260531.htm), *Segment Data*) | Building / Consumer Products |
| **PLPC** | Industrials / Water Sewer Pipeline Comm & Power Line Construction | Preformed Line Products — **manufactures** pole-line hardware, connectors and closures. It is not a contractor and books no construction-contract revenue | Q2-26 net sales **$212.7M** with **cost of *products* sold $139.7M**; segments are geographic (PLP-USA $104.3M, Americas $34.0M, EMEA $41.7M, Asia-Pacific $32.7M); product mix **Energy 70%** of revenue ([10-Q 2026-07-30](https://www.sec.gov/Archives/edgar/data/80035/000008003526000030/plpc-20260630.htm), *Revenue by Segment and Product Type* + *Segment Information*) | Electrical Products / Electrical Equipment |
| **OTTR** | Utilities / Electric Utilities: Central | Otter Tail — a PVC-pipe and metal-fabrication manufacturer with a regulated utility attached | Q2-26 operating revenue $334.4M: **Plastics $124.6M = 37.3% (largest segment)**, Electric $121.3M = 36.3%, Manufacturing $88.5M = 26.5% — **63.7% of revenue is non-utility** ([10-Q 2026-08-05](https://www.sec.gov/Archives/edgar/data/1466593/000146659326000071/ottr-20260630.htm), *Segment Profit or Loss*) | Diversified Industrials (or split) |
| **ARCC** | Finance / **Finance: Consumer Services** | Ares Capital — BDC lending to private US middle-market **companies**. Nothing consumer about it, and its seven peers in the same briefing all carry `Finance/Investors Services` | Gross investment income **$763M (Q1-26)**, $3,052M FY2025, earned on "first lien senior secured loans (incl. unitranche) and second lien senior secured loans" to private companies ([10-Q 2026-07-29](https://www.sec.gov/Archives/edgar/data/1287750/000162828026050307/arcc-20260630.htm), *Organization*; companyfacts `GrossInvestmentIncomeOperating`) | Finance/Investors Services (match its peers) |

### B. Pre-revenue companies carrying an operating-industry label

Same failure mode as the confirmed GFUZ case: the label asserts an operating business that produces no revenue. Included here because a field statistic that averages these in as if they were producers is corrupted by exactly the amount they are not.

| Ticker | Current label | Reality | Revenue evidence |
|---|---|---|---|
| **GFUZ** | Utilities / Electric Utilities: Central | General Fusion — pre-revenue fusion R&D; no commercial fusion plant exists anywhere | 20-F filed 2026-07-16 carries no segment or revenue R-file and companyfacts returns no revenue concept ([20-F](https://www.sec.gov/Archives/edgar/data/2074850/000110465926084015/tm2620136d1_20f.htm)). Confirmed in the calibration set |
| **OKLO** | Utilities / Electric Utilities: Central | Reactor developer; has never sold power | **Total revenue $1.210M for H1-26** — the first revenue in company history — against **net loss $(81.6)M** H1 and equity $3.27B ([10-Q 2026-08-07](https://www.sec.gov/Archives/edgar/data/1849056/000162828026054571/oklo-20260630.htm); companyfacts `Revenues`) |
| **NNE** | Utilities / Electric Utilities: Central | Nano Nuclear — reactor developer | **Revenue $214,042** for the quarter ended 30 Jun 2026 (recognised from 22 May 2026), **net loss $(10.1)M** in the same quarter ([10-Q](https://www.sec.gov/Archives/edgar/data/1923891/000149315226023071/form10-q.htm); companyfacts) |
| **FISN** | Utilities / Electric Utilities: Central | Deep Fission — pre-revenue borehole reactor developer | **No revenue concept reported at all**; H1-26 net loss $(52.4)M, Q2 $(31.0)M, cash $93.0M (companyfacts, 10-Q filed 2026-08-03) |
| **FRVO** | Utilities / Electric Utilities: Central | Fervo Energy — geothermal developer, Cape Station under construction | **Revenue $113K in Q2-26 / $174K H1-26** against **net loss $(87.7)M** H1 (companyfacts, 10-Q filed 2026-08-13) |
| **DC** | Basic Materials / Metal Mining | Dakota Gold — exploration only | **No revenue concept reported.** Q2-26 income statement is entirely expense: exploration $6.51M, G&A $2.73M; net loss $(8.35)M; the only inflow is interest income $869.5K ([10-Q 2026-08-12](https://www.sec.gov/Archives/edgar/data/1852353/000110465926094733/tmb-20260630x10q.htm), *Segment Information*) |
| **NB** | Basic Materials / Metal Mining | NioCorp — Elk Creek niobium/scandium project, pre-construction | **No revenue concept reported**; "one operating and reportable segment… includes the exploration…"; equity $435.4M, cash $419.2M funded by issuance ([10-Q 2026-05-14](https://www.sec.gov/Archives/edgar/data/1512228/000119312526223959/nb-20260331.htm)) |
| **CRML** | Basic Materials / Metal Mining | Critical Metals Corp — Tanbreez (Greenland), pilot plant stage | No consolidated revenue; the only revenue line in the 20-F is **$2.99M inside an equity-accounted joint venture**, of which the group's share of profit was $0.70M ([20-F 2025-10-06](https://www.sec.gov/Archives/edgar/data/1951089/000121390025096254/ea0257309-20f_critical.htm)) |
| **USAR** | Basic Materials / Metal Mining | USA Rare Earth — magnet/materials manufacturing at Stillwater; the Round Top deposit is not in production | Q2-26 revenue **$5.821M** (nil a year earlier), **70% of it international**, from four customers at 26/29/23/18% concentration — **no mining revenue is disclosed**; net loss $(10.3)M in the quarter ([10-Q 2026-08-10](https://www.sec.gov/Archives/edgar/data/1970622/000197062226000057/usar-20260630.htm), *Concentrations*) |

**Confirmed wrong: 24 of 117.**

---

## Suspicious, needs a human

Evidence is partial, or the label is technically defensible but functionally misleading for the thesis it is being used in.

| Ticker | Current label | Issue | Numbers |
|---|---|---|---|
| **BKR** | Consumer Discretionary / Oil and Gas Field Machinery | Half the company is not oilfield. Its own briefing (thesis 1) ranks it #1 *because* the non-oilfield half is booming | Q2-26 revenue $6,742M: **OFSE $3,451M = 51.2%**, Industrial & Energy Technology (gas turbines, LNG, power gen, industrial) **$3,291M = 48.8%**. IET is now larger in orders. A one-quarter mix shift flips the majority ([10-Q 2026-07-27](https://www.sec.gov/Archives/edgar/data/1701605/000170160526000023/bkr-20260630.htm)) |
| **CRS** | Industrials / Steel/Iron Ore | Carpenter Technology — premium alloys for aerospace. Its Specialty Alloys Operations segment does include stainless **steel**, and the filing states "further disaggregation of revenue is impracticable", so I cannot separate stainless from nickel/cobalt/titanium | FY2026 net sales $3,124.2M; **SAO $2,811.7M = 90%**; end market **Aerospace & Defense $2,035.2M = 65.1%**, Medical 8.9%, Energy 7.4% ([10-K 2026-08-12](https://www.sec.gov/Archives/edgar/data/17843/000001784326000034/crs-20260630.htm)) |
| **NWPX** | Industrials / Steel/Iron Ore | Water-infrastructure products, on a municipal-project cycle, not a steel-price cycle. 71% is engineered steel water pipe (a steel product — hence not "plainly different"), but 29% is precast **concrete** | Q2-26 net sales $159.5M: **Water Transmission Systems $113.2M = 71.0%**, **Precast Infrastructure & Engineered Systems $46.3M = 29.0%** ([10-Q 2026-07-30](https://www.sec.gov/Archives/edgar/data/1001385/000143774926025050/nwpx20260630_10q.htm)) |
| **TS** | Industrials / Steel/Iron Ore | Tenaris does make steel (seamless OCTG), so the industry label is arguably right — but its revenue is driven by drilling activity, not steel demand. Grouping it with mills in a steel-spread thesis inverts the sign | FY2025 net sales $11,981M; **Tubes $11,400M**, of which **oil & natural gas $10,172M = 84.9% of consolidated revenue**; industrial/power $671M ([20-F 2026-03-31](https://www.sec.gov/Archives/edgar/data/1190723/000155485526000490/ts-20251231.htm)) |
| **LAR** | Basic Materials / Metal Mining | Lithium Argentina's only asset is an equity-accounted JV stake, so consolidated revenue is zero — the label cannot be confirmed or refuted by the revenue test. The commodity is also lithium, not a base/precious metal | **No revenue reported since FY2018** ($4.8M). FY2025 loss $(76.9)M, equity $816.9M ([20-F 2026-03-23](https://www.sec.gov/Archives/edgar/data/1440972/000119312526118478/lar-20251231.htm); companyfacts) |

**Suspicious: 5 of 117.**

---

## Verified correct

87 of 117. The label's named business is the dominant revenue source, confirmed from the filing. Percentages are of total revenue in the cited period.

**Oilfield — 9/12 correct.** OIS (Offshore Manufactured Products $92.7M + Completion & Production Services $24.3M = 100% of $156.7M) · HMH (ESS $97.7M + PCS $73.2M of $170.8M) · FTI (Subsea $2,486.9M of $2,763.1M = 90%) · WHD (Pressure Control $344.0M of $449.5M = 76.5%) · INVX ($244.9M, all oilfield product/service/rental) · FLOC (Production Solutions $170.9M of $235.9M; balance Natural Gas Technologies) · NOV (Energy Equipment $1,218M + Energy Products & Services $974M of $2,134M = 100%) · WFRD (DRE $291M + WCC $433M + PRI $316M of $1,105M = 100%) · FET ($226.2M, all oilfield product lines).

**Utilities — 32/38 correct.** SO (retail electric $4,814M of $6,977M operating revenue) · D ($4,480M regulated electric/gas) · AEP (retail $3,980M of $5,445M) · CEG (power & power-related $4,959M of $7,504M) · VST · FE (distribution $1,714M of $3,692M, all wires/regulated) · PPL · NEE ($7,534M, 2 utility/energy-resources segments) · TLN ($747M generation) · ORA ($258.8M geothermal electricity + products) · PNW ($1,455.7M, retail electric) · AES ($3,422M) · RNW (sale of power ₨88,196M = 66.7% of ₨132,196M — *note: 30.9% is solar-module manufacturing*) · ES ($2,903M regulated T&D) · FTS (electric+gas revenue C$11,584M) · MGEE (electric $131.4M of $161.2M = 81.5%, gas $29.6M) · ETR ($3,523.6M) · DTE (electric $1,775M of $3,369M + gas) · IDA ($469.8M) · OGE ($711.9M) · CNP (Houston Electric $1,167M + CERC gas of $2,152M) · BEP (hydro $2,741M + wind $1,620M + solar $1,316M of $6,407M) · BEPC ($3,728M, same assets) · TXNM (electric operating revenue $548.6M) · CWEN (Renewables & Storage $395M + Flexible Generation $86M of $481M) · NRG ($7,481M generation + retail) · EIX ($4,357M) · AQN ($2,433.6M regulated) · KEP (T&D ₩94.7tn + nuclear generation ₩15.3tn + non-nuclear ₩28.7tn) · TAC ($2,405M power) · HNRG (Electric Operations $59.5M vs Coal Operations $50.9M of $101.5M consolidated — *note: ~41% of external revenue is third-party coal mining*) · HE (Electric utility $936.9M of $939.7M = 99.7%; the bank was sold 31 Dec 2024).

**Grocery — 7/9 correct.** KR (retail operations $46,121M, "substantially all") · SFM ($2,325.8M; perishables 57.2% / non-perishables 42.8%) · TBBB (Ps.78.0bn; private label 58%, branded 36% — Mexican hard-discount grocery) · IMKTA (retail grocery $1,310.1M of $1,368.3M = 95.7%; fuel $213.6M = 15.6% of total) · NGVC (grocery 73%, dietary supplements 18%) · GO ($1,192.8M, single grocery segment) · ACI ($24,941.6M, one retail food segment).

**Metals — 13/22 correct.** SCCO (copper $3,116.8M of $4,289.0M = 72.7%) · FCX (copper cathode+rod+concentrate+purchased $5,320M of $7,029M = 75.7%; gold $640M, moly $728M) · RIO ($57,638M FY2025, iron ore/copper/aluminium) · VALE (iron ore $25,010M + pellets $4,396M + copper $3,753M + nickel of $38,403M) · HBM ($2,211.0M FY2025 mine revenue) · ERO ($785.8M from 3 operating copper/gold mines) · BVN ($1,604.4M from named mining units) · NEXA (zinc $1,590M + lead $539M + copper $505M + silver $108M of $3,002M) · MP (NdPr oxide & metal $94.4M of $108.5M = 87%) · ASM ($92.2M FY2025 silver/gold) · USAS (silver $61.8M of $82.5M sales revenue) · SGML ($110.0M FY2025 lithium concentrate) · AUGO (six operating gold/copper mines, H1-26 production 157,574 GEO, H1 adj. EBITDA US$441M — [6-K 2026-08-05](https://www.sec.gov/Archives/edgar/data/1468642/000117184326005263/exh_991.htm); no XBRL segment file exists for this filer).

**Steel — 10/18 correct.** NUE (sheet $2,916M + bar $1,862M + structural $847M + plate $856M + tubular $599M of $10,397M) · STLD (Steel Operations $3,744M external of $6,091.6M; balance recycling/fabrication/aluminium) · TX (hot-rolled $6,425M + coated $5,304M + cold-rolled $2,362M of $15,609M) · MT (steel sales $52,950M of $61,352M = 86.3%) · CMC (North America Steel $1,810M of $2,483M = 72.9%) · MTUS (bar $221.1M of $341.0M = 64.8%, tube $35.6M) · FRD (flat-roll $221.8M + tubular $18.2M of $240.0M) · IIIN (welded wire reinforcement $123.7M + PC strand $73.9M = 100% of $197.7M) · WS ($3,443.8M FY2026 steel processing) · PKX (Steel ₩37,285bn of ₩68,987bn = **54.0%** — *note: Trading is ₩23,744bn = 34.4%, so the majority is thin*).

**Construction — 9/10 correct.** PWR ($9,557.0M electric/infrastructure construction) · EME ($5,154.9M; US electrical $1,662.5M + US mechanical $2,300.9M) · FIX ($3,265.7M; 75.1% from the largest end market) · IESC ($1,242.7M; Communications, Residential, Infrastructure Solutions, C&I) · AGX ($291.0M power-plant EPC) · LMB ($173.5M) · MTRX ($210.5M) · HUBB (Utility Solutions $1,025.8M + Electrical Solutions $686.0M of $1,711.8M — "Electrical Products" holds) · ITRI ($562.9M metering/grid-edge — "Electrical Products" holds).

**BDCs — 7/8 correct.** All earn gross investment income from private-company debt, matching `Finance/Investors Services`: MAIN ($149.6M Q2-26) · FDUS ($43.5M) · SLRC ($48.8M) · BCSF ($62.3M) · NMFC ($61.5M) · CION ($49.8M) · MFIC ($68.2M).

---

## Unknown / no evidence reachable

| Ticker | Current label | Why |
|---|---|---|
| **GMTL** | Basic Materials / Metal Mining | Guardian Metal Resources plc files **only 6-K and 13G forms** — no 10-K, 10-Q, 20-F or 40-F exists in EDGAR, and `companyfacts` returns nothing. There is therefore **no revenue figure of any kind** to test the label against. Its 6-K titles (e.g. "Pilot Mountain Pre-Feasibility Study Results", 2026-06-30) indicate a pre-construction tungsten project, but a filing title is not revenue evidence. Marked UNKNOWN rather than guessed. |

Also worth a human's attention, though outside the label test: **HDRN (Hadron Energy)** is named as an in-play utilities name in `target_groups_2026-08-11.md` but **is absent from `broad_sectors.csv` entirely** (2,991 symbols; HDRN is not one of them). Its filings show revenue of **$0** for FY2025 and Q1-2026. That is a coverage gap rather than a mislabel.

---

## A second, separate defect: the `GICS Sector` column contradicts itself

The audit above concerns the `GICS Sub-Industry` column. The `GICS Sector` column has an independent problem — **the same sub-industry is assigned to different sectors for different companies**, which no classification scheme permits:

- `Electric Utilities: Central` → **Utilities ×43, Energy ×1 (MGEE), Industrials ×1 (AES)**
- `Engineering & Construction` → **Industrials ×4, Consumer Discretionary ×6** (PWR/EME/FIX/IESC are Industrials; AGX/LMB/MTRX are Consumer Discretionary)
- `Electrical Products` → **Technology ×16, Industrials ×8, Energy ×2**

Across the whole file, **32 of 169 sub-industries map to more than one sector**. Separately, all 12 `Oil and Gas Field Machinery` names (BKR, NOV, FTI, WHD, WFRD, FET, OIS, DNOW, INVX, HMH, FLOC, SEI) sit in **Consumer Discretionary**, while all 13 `Oilfield Services/Equipment` names (SLB, HAL, LBRT, PUMP, ACDC …) sit in **Energy** — two halves of one industry split across two sectors. Any code that aggregates by `GICS Sector` is mixing these.

---

## Estimated contamination

**Sample size: 117 companies** — every name ranked or explicitly named in the seven live rank-thesis and target-group briefings. Not a random sample of the 2,990-name universe; it is the exact set whose labels can corrupt a current conclusion.

| Verdict | Count | Share of 117 |
|---|---|---|
| Confirmed wrong | **24** | **20.5%** |
| Suspicious (needs a human) | 5 | 4.3% |
| Verified correct | 87 | 74.4% |
| Unknown | 1 | 0.9% |

Confirmed-wrong split by failure mode: **15 operating mislabels (12.8%)** and **9 pre-revenue shells wearing an operating label (7.7%)**.

**By group, worst first (confirmed wrong / group size):**

| Group | Wrong | Size | Rate | Character of the failure |
|---|---|---|---|---|
| **Metals** | 7 | 22 | **31.8%** | Worst overall, but 4 of the 7 are pre-revenue explorers. Operating-mislabel rate is 3/22 = 13.6% |
| **Steel** | 5 | 18 | **27.8%** | **Worst on real operating businesses** — every one of the 5 (TWI, ATI, SXC, ROCK, WOR) is a live company earning real money from something other than steel. Add the 3 suspicious (CRS, NWPX, TS) and **8 of 18 = 44%** of the "steel" field is questionable |
| Grocery | 2 | 9 | 22.2% | Both are the same error: convenience-store/fuel retailers filed as grocery chains (ARKO, YSWY). Fuel is 84% and 73% of their revenue |
| Oilfield | 2 | 12 | 16.7% | SEI (power) and DNOW (distribution); BKR is 51/49 and one quarter from joining them |
| Utilities | 6 | 38 | 15.8% | 5 of the 6 are pre-revenue reactor/fusion/geothermal developers. Only OTTR is an operating mislabel — but it is a large one (63.7% non-utility revenue) |
| BDC | 1 | 8 | 12.5% | ARCC alone; and it is inconsistent with its own seven peers |
| Construction | 1 | 10 | 10.0% | PLPC (a manufacturer filed as a contractor) |

**How to read this.** The regulated-utility and BDC cores are clean: large, stable, correctly-bucketed companies. The damage concentrates in exactly two places — (1) **the steel field, where more than a quarter of the members do not produce steel**, so any field-level statistic about steel spreads is averaging in tyres, jet-engine alloys, coke, roofing accessories and propane tanks; and (2) **the small/micro-cap tail everywhere**, where SPAC de-mergers and reverse mergers (ALOY, GFUZ, FISN, FRVO, USAR, OKLO, NNE) leave the registrant's original SIC code attached to a completely different company. A field's median return is safe; a field's *dispersion*, *cohesion* and *worst-mover* statistics are not, because the mislabelled names cluster in the tails.

---

*Method note: this audit tested only revenue. It did not test whether a correctly-labelled company belongs in a given thesis (e.g. TS is genuinely a steel-pipe maker but trades on rig counts; AUGO is genuinely a miner but of gold, not copper). Those are thesis-construction questions, flagged where relevant but not counted as label errors.*
