# Placeholder market data and regulation (research for spec #1, ticket #4)

Research date: 2026-11-24; regulation, taxes, Export Price and Discount Rate re-checked against primary sources on
2026-11-25 (ticket #32, section 9, which supersedes the earlier statements about them). All values are **placeholders** for the data files of spec #1. They are market averages or
manufacturer datasheet values, not any company's real prices. No company-specific or personal data is used.

Legend for the **Kind** column:

- **Direct**: copied from a primary source (regulation text, EPDK table, manufacturer datasheet, price index).
- **Derived**: computed from direct figures; the derivation is written next to it.
- **Estimate**: no primary source found; a judgment value with its reasoning. Replace when real data arrives.

Confidence is stated where the source is secondary. "Secondary" means a trade or news site, not the regulation text.

## 0. Findings that need a repo owner decision

Three findings touch the design of spec #1. The repo owner decided them on 2026-11-24; see section 7 "Decisions".

### F1. Hourly vs monthly netting: monthly for residential. No contradiction. (Resolved in favour of spec #1.)

- The 2 April 2026 amendment to the Lisanssız Elektrik Üretim Yönetmeliği (Resmî Gazete 33212) makes netting
  (mahsuplaşma) **hourly in general** (amended Madde 26(1)) but keeps it **monthly for plants tied to mesken
  consumption facilities**: amended Madde 26(20), "piyasa işletmecisi tarafından aylık olarak yürütülür".
- Madde 26 takes effect on 1 May 2026 (Madde 26 of the amendment, item (a)). That date has passed.
- Consequence: the Self-Consumption Ratio is a *monthly* match, which is high (see section 3). If netting were hourly the
  ratio would be far lower and the "ratio" approach would be weak. It is not hourly for residential, so the spec holds.
- Caveat: the amendment text was read through a fetch tool and was partly garbled; see "Verification gaps" below. **Verified in section 9** against the full Resmî Gazete text.
- Source: <https://www.resmigazete.gov.tr/eskiler/2026/04/20260402-4.htm> (Resmî Gazete 2026-04-02, no. 33212).

### F2. Capacity cap: tied to Contracted Power, no absolute residential kW cap found. (Consistent with spec #1; default is not regulatory.)

- Original regulation (Resmî Gazete 12 May 2019, no. 30772), Madde 7(10): installed capacity of the plant "ilişkilendirilecek
  tüketim tesisinin bağlantı anlaşmasındaki sözleşme gücünden fazla olamaz". Madde 11(3) repeats it. Source:
  <https://www.resmigazete.gov.tr/eskiler/2019/05/20190512-1.htm>. Only the first ~40% of this page was readable.
- 2026 amendment, Madde 28(5) as replaced: the contracted power of the linked consumption facilities cannot be less than
  the installed capacity (the exception (b) covers municipal, industrial and irrigation consumers, not mesken).
- "Installed capacity" is the electrical (inverter AC) capacity. Amended Madde 17(7): requested *mechanical* (panel DC)
  capacity "elektriksel kurulu gücün iki katını aşamaz", so DC/AC up to 2.0 is legal. This matches the spec's rule
  (inverter AC at most Contracted Power; panels capped by the usable inverter AC power times the maximum DC/AC Ratio,
  where the usable AC power is that of the largest Catalog inverter within the Contracted Power).
- Madde 26(17) as amended: annual production may not exceed twice annual consumption, and that rule explicitly does **not**
  apply to plants linked to mesken consumption facilities. So there is no consumption-based cap for residential.
- The only "10 kW" in the regulation text is Madde 11(1): a "tip proje" (simplified type-project) threshold of 10 kW. It is a
  paperwork threshold, not a cap. No 5 kW or 10 kW residential cap was found in the readable text.
- **The spec's default Contracted Power of 10 kW is not a regulatory figure.** It is an installer placeholder. A real default
  would come from the connection agreement (typically tied to the Customer's phase and meter). Keep 10 kW as a clearly marked
  placeholder. **DECIDED (2026-11-24): Option A**, keep 10 kW as a marked installer assumption, recorded as defaulted.
  - Option A (keep 10 kW default): quotes work without the agreement; the Quote must say the figure is assumed (the spec
    already records "given or defaulted"). Risk: a customer with a smaller connection gets an oversized system.
  - Option B (require it): safest, but breaks user story 17.

### F3. DECIDED (marginal bands) - the residential Tariff Tier is a daily 8 kWh marginal band, not an annual whole-bill threshold.

- The EPDK tariff table valid from 4 April 2026 has two mesken (AG tek terim) rows: "Mesken (8 kWh/gün ve altı)" and
  "Mesken (8 kWh/gün üstü)". The table's own note (truncated in the file) says the low price applies to consumption up to a
  billing-period **average of 8 kWh/day**. The high price applies to the part above it.
- Spec #1 models the tier as: compare *annual* consumption to a threshold, then price **all** energy at one tier.
- The real band is marginal. The annual-equivalent threshold is 8 x 365 = **2,920 kWh/year** (2,928 in a leap year).
  A customer using 6,000 kWh/year pays the low price for 2,920 kWh and the high price for 3,080 kWh.
- Solar offsets billed consumption from the top, so a customer above the threshold saves at the **high** price until their
  billed consumption falls to the threshold, then at the low price. A single tier for all self-consumed energy therefore
  overstates savings for customers who end up near or below the threshold, and understates them for the largest users.
- Options for the spec:
  - Option A (keep the spec's single tier): set threshold 2,920 kWh/year. Simple. Savings are approximate for
    households close to the threshold; document as an approximation.
  - Option B (marginal bands): the domain carries both prices and the threshold; bill-to-kWh conversion and the savings split
    become piecewise. More accurate; affects the "Consumption rules" and "Annual Savings" sections and their tests.
- A separate rule is easy to confuse with this one: the **Son Kaynak Tedarik Tarifesi (SKTT) annual limit** for mesken is
  4,000 kWh/year in 2026 (EPDK Kurul Karari 13912 of 2025-10-30, effective 2026-01-01). Above it, a customer without a bilateral
  contract is moved to the high-consumption last-resort tariff. This is not the tier above and should not be used as the
  Tariff Tier threshold. A claim that the limit becomes 3,000 kWh from 2027 appeared in one secondary source only and is **unverified**.

### F4. DECIDED (real rates) - nominal TRY escalation over 25 years is not meaningful.

- TCMB Market Participants Survey, November 2026: year-end 2026 CPI expectation 30.04%, 12-month-ahead 24.04%, 24-month-ahead
  18.02%; USD/TRY year-end 2026 51.61, 12-month-ahead 60.77. Sources are secondary reports of the survey (below).
- A nominal TRY cash flow over 25 years with undiscounted payback would need tariff escalation near inflation (18-24%/year).
  That compounds to a factor of ~50-80 by year 25 and makes "lifetime savings" meaningless.
- Proposed (Estimate): model in **real terms**: tariff escalation and equipment price escalation are *real* rates (section 6).
  This needs a decision because it changes how the Quote must be explained to the Customer ("in today's money").
  - Option A (real terms, proposed): small escalation rates (2% and 0%), payback in today's lira; lifetime table is in constant lira.
  - Option B (nominal): escalation 18-24% for the tariff and a matching FX-driven rate for equipment; payback is short, lifetime
    totals are large nominal numbers; needs a stated inflation path.

## 1. Regulation summary

| Point | Finding | Source | Source date | Kind |
|---|---|---|---|---|
| Capacity cap | Installed (electrical) capacity limited by Contracted Power of the linked consumption facility; no absolute mesken kW cap in the readable text | Resmî Gazete 30772 Madde 7(10), 11(3); amendment Madde 28(5) | 2019-05-12; 2026-04-02 | Direct (partly garbled text) |
| Mechanical vs electrical | Panel DC capacity up to 2x electrical (inverter AC) | Amendment Madde 17(7) | 2026-04-02 | Direct |
| Mesken netting | Monthly | Amendment Madde 26(20) | 2026-04-02, in force 2026-05-01 | Direct |
| Production cap 2x consumption | Not applied to mesken | Amendment Madde 26(17) | 2026-04-02 | Direct |
| Surplus energy | Surplus energy fed to the grid is valued under YEKDEM through the supplier | Original Madde 5(2) | 2019-05-12 | Direct |
| Tariff tier | 8 kWh/day marginal band | EPDK tariff table | valid 2026-04-04 | Direct (see F3) |
| SKTT limit | 4,000 kWh/year (different rule) | EPDK Kurul Karari 13912, via GENSED | 2025-10-30 | Secondary |

URLs: <https://www.resmigazete.gov.tr/eskiler/2026/04/20260402-4.htm>, <https://www.resmigazete.gov.tr/eskiler/2019/05/20190512-1.htm>,
<https://gensed.org/mesken-elektriginde-yeni-kademe-4-000-kwhe-dusuruldu/>.

### Verification gaps

- The consolidated regulation on mevzuat.gov.tr could not be loaded (404 page). Madde numbers above come from the Resmî Gazete texts.
  The fetch tool garbled Turkish characters and cut the 2019 text after about 40%. The owner should confirm F1 and F2 against
  the consolidated text before the data files are treated as final.
- Whether unused monthly surplus is carried to the next month or year (devir) was not found in the readable text.
- The Resmî Gazete texts carry no EPDK Kurul Karari number for the amendment. Decision 14531 (2026-04-30, usul ve esaslar for
  hourly netting) was reported only by a secondary source (<https://yesilhaber.net/epdk-lisanssiz-mahsuplasma-saatlik-sistem/>).

## 2. Catalog

### 2.1 Panels (residential, full-size 54-cell n-type, about 440 W)

Datasheet values (Direct). USD unit price is an Estimate (section 2.3). Area = length x width.

| Model | Power (W) | Dimensions (mm) | Area (m2) | Degradation | Source | Datasheet date |
|---|---|---|---|---|---|---|
| Jinko Tiger Neo JKM440N-54HL4-(V) | 440 | 1722 x 1134 x 30 | 1.953 | first year 1%, then 0.40%/yr; 30-year guarantee 87.4% | <https://www.solarquotes.com.au/wp-content/uploads/2023/04/Jinko-tiger-neo-440.pdf> | 2022 (file `...F2C2-EN-AU`) |
| Trina Vertex S+ TSM-NEG9RH.25 (440 W column) | 440 | 1762 x 1134 x 35 | 1.998 | first year 1%, then 0.40%/yr; 30-year power guarantee | <https://www-cdn.trinasolar.com/wwwstorage/sites/17/DT-M-0130-NA-EN-A-Datasheet_Vertex-S_NEG9RH.25_2026_A.pdf> | PDF saved 2026-05-27 |
| Trina Vertex S+ TSM-NE09RH.05 (440 W column) | 440 | 1762 x 1134 x 35 | 1.998 | "First-year degradation 1% and annual degradation at 0.4%"; 25-year power guarantee | <https://www-cdn.trinasolar.com/wwwstorage/sites/17/VertexS_TSM-NE09RH.05_420-445W_2025_A.pdf> | PDF saved 2025-04-30 |

Notes:

- **Annual degradation rate for the data file (Derived): 0.47%/yr.** The spec has a single rate: year-n output = year-1 x
  (1 - d)^(n-1). The datasheets guarantee 1% in year 1 then 0.4%/yr. Guaranteed power at year 25 is 99% - 24 x 0.4% = 89.4%
  (Jinko's 30-year figure 87.4% = 99% - 29 x 0.4% confirms the arithmetic). The constant rate that gives 0.894 at year 25
  is 1 - 0.894^(1/24) = 0.47%. This is a guarantee (worst case), not a typical field value.
- Areas are derived: 1.722 x 1.134 = 1.953 m2; 1.762 x 1.134 = 1.998 m2.
- The Jinko sheet I could read is a 2022 regional edition; the dimensions of the current Jinko 440 W model may differ. The
  Trina NEG9RH.25 rows were read from a PDF whose Trina sheet was text-extracted; the 440 W column was identified from the
  power table, and the dimension line shows 1762 x 1134 x 35 mm.
- LONGi was tried as a third maker; its residential-size datasheet could not be read, so none is proposed.
- **Proposed Default Panel: Trina Vertex S+ TSM-NEG9RH.25, 440 W** (full black, dual glass, 30-year power guarantee, 2026 datasheet).

### 2.2 Inverters (string, three-phase, Huawei SUN2000-M1 family)

Datasheet: Huawei SUN2000-3/4/5/6/8/10KTL-M1, version 01-(20190401), <https://www.solartraders.com/uploads/production/data_sheet/file/7599/Datasheet_SUN2000MA-3-20KTL-M_1_2.pdf>
(a distributor-hosted copy; the Huawei-hosted file could not be downloaded). Rated AC power is the model number
(3 / 5 / 8 / 10 kW). "Recommended max PV" is the datasheet row.

| Model | AC power (kW) | Recommended max PV (Wp) | Max efficiency | USD price (Estimate) |
|---|---|---|---|---|
| SUN2000-3KTL-M1 | 3 | 6,150 | 98.2% | 650 |
| SUN2000-4KTL-M1 | 4 | (see datasheet) | (see datasheet) | 725 (interpolated, added in ticket #7) |
| SUN2000-5KTL-M1 | 5 | 10,250 | 98.4% | 800 |
| SUN2000-6KTL-M1 | 6 | (see datasheet) | (see datasheet) | 900 (interpolated, added in ticket #7) |
| SUN2000-8KTL-M1 | 8 | 14,880 | 98.6% | 1,050 |
| SUN2000-10KTL-M1 | 10 | 14,880 | 98.6% | 1,200 |

Notes:

- Spec check: the 8 and 10 kW rows list the same 14,880 Wp in the file I read; this may be a datasheet quirk. Do not depend on
  that column. The DC/AC Ratio limits in section 5 come from the spec, not from this column.
- The datasheet is dated 2019. Newer revisions may exist. Warranty is not stated in the part I read.
- No distributor price list was reachable. **Prices are Estimates**: marketplace asking prices for the 10KTL-M1 found
  in 2026 ranged from about EUR 750 (used) to EUR 1,390 ex-VAT (new, Germany) (<https://www.secondsol.com/en/anzeige/48793//huawei/sun2000-10ktl-m1>).
  The 10 kW figure uses about EUR 1,000 x 1.15 USD/EUR = ~1,150, rounded to 1,200 for a Turkish importer's margin. The smaller
  models scale at roughly USD 150-217 per kW with a fixed-cost floor. Treat all four as low-confidence.

### 2.3 Panel unit price (Estimate)

- InfoLink spot price, week 12-18 Nov 2026 (published 2026-11-18): TOPCon module, Europe projects, China made, FOB **USD 0.115/W**;
  BC all-black module, Europe residential projects, China made, FOB **USD 0.190/W** (Direct).
  <https://www.infolink-group.com/energy-article/pv-spot-price-20261118>.
- Estimate for a Turkish importer's price, delivered, for a 440 W full-black panel: **USD 0.17/W = USD 75 per panel**. The point sits
  between the TOPCon and the all-black residential figures and adds a freight/customs/distributor uplift. Turkey's import duty on
  Chinese modules was not researched and may raise this.
- Proposed per-panel prices: Jinko JKM440N-54HL4-(V) **USD 72**; Trina NEG9RH.25 **USD 76**; Trina NE09RH.05 **USD 74**.
  The differences are illustrative, not sourced.

## 3. Residential tariff

> Status (ticket #33): the fixed ratio proposed in this section (the last table row and the derivation after it) was replaced by Monthly Netting ([ADR 0005](../adr/0005-monthly-netting-replaces-self-consumption-ratio.md)). It is no longer an input; each System Option reports a Netted Share as a result. The derivation is kept as the history of how it was found.

| Value | Proposed | Unit | Source / derivation | Source date | Kind |
|---|---|---|---|---|---|
| Tariff Tier threshold | 2,920 | kWh/year | 8 kWh/day x 365; marginal band boundary (F3, decided) | table valid 2026-04-04 | Derived |
| Low-tier energy + distribution, ex-tax | 2.9190 | TRY/kWh | (49.4065 + 242.49) kr/kWh from the EPDK table, AG tek terim "Mesken (8 kWh/gun ve alti)" | 2026-04-04 | Direct |
| High-tier energy + distribution, ex-tax | 4.3207 | TRY/kWh | (189.5808 + 242.49) kr/kWh, "Mesken (8 kWh/gun ustu)" | 2026-04-04 | Direct |
| **Low all-in Retail Tariff** | **3.24** | TRY/kWh | (1.05 x 0.494065 + 2.4249) x 1.10 = 3.2380 | 2026-04-04 | Derived |
| **High all-in Retail Tariff** | **4.86** | TRY/kWh | (1.05 x 1.895808 + 2.4249) x 1.10 = 4.8570 | 2026-04-04 | Derived |
| Export Price | 2.92 | TRY/kWh | YEKDEM solar price 292.49 kr/kWh, EPIAS, effective 2026-11-01; **unverified for new residential plants** | 2026-11-01 | Estimate |
| Export Price valid-from | 2026-11-01 | date | same | 2026-11-01 | Estimate |
| Self-Consumption Ratio | 0.85 | share | monthly netting (F1); derivation below | 2026-11-24 | Derived |

EPDK table (Direct): the file "4 Nisan 2026 Tarihinden Itibaren Gecerli Vergiler Haric Elektrik Tarifeleri", downloaded from the
EPDK site linked on <https://gensed.org/4-nisan-2026dan-itibaren-uygulanacak-elektrik-tarifeleri-yayimlandi/> via
<https://www.epdk.gov.tr/Detay/DownloadDocument?id=pI+XZjfJIU0=>. The EPDK pages that should list later tables
(<https://www.epdk.gov.tr/Detay/Icerik/3-1327/elektrik-faturalarina-esas-tarife-tablolari>) did not render rows, and no 1 July or
1 October 2026 table was found by two secondary sources. It is possible, but unconfirmed, that a later table exists.
The tariff changes quarterly, so the data file must carry its valid-from date.

Taxes (Secondary, <https://enerjiajansi.com.tr/elektrik-birim-fiyatlari/>, updated 2026-10-25): BTV (belediye tuketim vergisi) 5% on
the energy charge only; KDV **10%** for konut (20% for commercial). Formula: price = (1.05 x energy + distribution) x 1.10.
The 5% BTV and the 10% KDV were not confirmed from a legal text; an EPDK page quoted only 0% and 1% BTV rates in another context.
If KDV were 20%, the all-in prices would be 3.53 and 5.30 TRY/kWh. **Verify before the data file is final.**

**Export Price (superseded by section 9.2: 1.24 TRY/kWh; the 2.92 below does not apply to a new residential plant).** Original Madde 5(2) values surplus energy "YEKDEM kapsaminda". The YEKDEM solar unit price table (EPIAS, via
<https://enerjiajansi.com.tr/yekdem-fiyatlari/>, 2026-11-02) shows 292.49 kr/kWh from 2026-11-01. A 90%-of-YEKDEM rule capped at the PTF (Presidential
Decision 11415 of 2026-06-12) applies to plants that have **completed** their 10-year support period, not to a new residential
plant. Distribution fees on the export side ("Lisanssiz Uretici 1/2", 208.1065 and 65.6008 kr/kWh in the EPDK table) may reduce the
net price. Their application to new residential plants was not established. So 2.92 TRY/kWh is an indicative upper estimate.

**Self-Consumption Ratio derivation (Derived).** Under monthly netting the ratio is the share of annual production that is matched
by consumption within the same month. I took PVGIS-SARAH3 monthly output for 1 kWp (loss 14%, tilt 30 degrees, south; PVGIS 5.3 call on
2026-11-24) and compared it with a flat monthly consumption and with a mild seasonal profile for a Consumption-Matched system
(annual production = annual consumption):

| City | Annual yield (kWh/kWp) | Netted share, flat consumption | Netted share, seasonal profile |
|---|---|---|---|
| Ankara | 1,472 | 0.88 | 0.87 |
| Istanbul | 1,368 | 0.85 | 0.84 |
| Antalya | 1,646 | 0.92 | 0.90 |

Proposed ratio **0.85** (the Istanbul end, which is the low end and the largest market). A Roof-Max system that is larger than
consumption would have a lower ratio, so the single ratio is an approximation; for a system at 80% of consumption the share rises
to 0.96-1.0. The seasonal profile is my illustrative assumption, not a measured profile. PVGIS call:
<https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat=39.93&lon=32.86&peakpower=1&loss=14&angle=30&aspect=0&outputformat=json>.

## 4. Pricing

| Value | Proposed | Unit | Derivation | Date | Kind |
|---|---|---|---|---|---|
| BOS (mounting and cabling) | 120 | USD/kWp | typical pitched-roof rails, clamps, DC/AC cable, protection; see cross-check | 2026-11-24 | Estimate |
| Labour | 4,000 | TRY/kWp | about USD 80/kWp at 50.4 TRY/USD | 2026-11-24 | Estimate |
| Fixed project cost | 20,000 | TRY | permits, project file, grid application, meter change; about USD 400 | 2026-11-24 | Estimate |
| Margin | 25% | share | see cross-check | 2026-11-24 | Estimate |
| VAT rate | 20% | share | general KDV rate; verified for a residential PV sale in section 9.1 | 2026-11-25 | Direct |

Cross-check against a 2026 market price. A Turkish industry article gives USD 9,000-10,000 + VAT for an average 10 kW system
with panels, inverter, cabling and paperwork (hybrid) (<https://uzmanpara.milliyet.com.tr/uzmanpara/elektrik-faturasini-dusurmek-isteyenler-dikkat-gunes-paneli-kurmanin-maliyeti-ne-kadar-7696820>, 2026; unnamed source, low confidence).
Model for 10 kWp (23 panels x USD 76 = 1,748; at 440 W that is 10.12 kWp):

- panels 1,748 + inverter 1,200 + BOS 1,214 = USD 4,162 = 209,800 TRY at 50.4;
- labour 40,480 TRY + fixed 20,000 TRY -> Installation Cost 270,300 TRY (about USD 5,360);
- x 1.25 margin = 337,900 TRY (about USD 6,700 ex-VAT); with 20% VAT 405,500 TRY (about USD 8,050).

This sits below the article's USD 9,000-10,000 + VAT (which includes a hybrid inverter and paperwork). So the margin and BOS
are on the low side of the market; the owner may raise them. VAT: the article quotes 20% on residential PV systems.

Example exchange rate for tests only (the service fetches TCMB at runtime): about **50.4 TRY/USD** around 2026-11-19, from news
tickers (<https://www.foreks.com/haber/detay/6afd4cf595131d72027df65d/FRKS/tr/tcmb-nin-19-kasim-2026-icin-acikladigi-gecici-piyasa-rezervi-122002-50-milyon-tl-18-11-26/>);
this is a market quote, **not a TCMB selling rate**. The official TCMB rate was not retrieved.

## 5. Engineering assumptions

| Value | Proposed | Unit | Derivation / source | Kind |
|---|---|---|---|---|
| Coverage Ratio, pitched | 0.80 | share | allows edge and fire-access setbacks; flush panels follow the roof | Estimate |
| Coverage Ratio, flat | 0.50 | share | row-spacing calculation below | Derived |
| Flat-roof tilt | 15 | degrees | low tilt limits row spacing and wind load; typical rack choice | Estimate |
| DC/AC Ratio minimum | 1.00 | ratio | below 1 wastes inverter capacity | Estimate |
| DC/AC Ratio maximum | 1.50 | ratio | raised from 1.30 in ticket #7: with 1.30 a 9-panel 3.96 kWp system fit no inverter (1.32 on 3 kW, 0.99 on 4 kW); still conservative; the regulation allows up to 2.0 mechanical/electrical (F2), Huawei recommends up to ~2.0 for small units | Estimate |
| System loss | 14 | % | PVGIS default loss for the PVcalc tool (the spec's 14%); PVGIS applies it | Direct (PVGIS default) |

Flat-roof Coverage Ratio derivation (portrait panel 1.762 m, tilt 15 degrees, latitude 40 degrees):

- Winter-solstice noon sun elevation = 90 - 40 - 23.4 = 26.6 degrees.
- Panel height above roof = 1.762 x sin(15) = 0.456 m; shadow length = 0.456 / tan(26.6) = 0.91 m.
- Footprint of the panel = 1.762 x cos(15) = 1.70 m; row pitch = 1.70 + 0.91 = 2.61 m.
- Ground coverage = 1.762 / 2.61 = 0.67; x 0.75 allowance for edges and walkways = **0.50**.

## 6. Financial assumptions

| Value | Proposed | Unit | Derivation | Kind |
|---|---|---|---|---|
| Tariff escalation | 2 | %/year (real) | real rate (F4, decided); nominal would be 18-24% | Estimate |
| Equipment price escalation (inverter replacement) | 0 | %/year (real) | real rate (F4, decided); module/inverter prices flat to falling in real terms | Estimate |
| System lifetime | 25 | years | product warranty 25 years on all three panels; 30-year power guarantees on two of them | Direct (datasheets) |
| Inverter replacement year | 12 | year | typical string-inverter warranty of 10 years plus margin; warranty not read from the Huawei sheet | Estimate |
| Validity Period | 15 | days | USD/TRY moved from 43.99 (2026-03-05) to about 50.4 (2026-11-19), about 1.5% a month, so 15 days is about 0.8% drift | Derived |

TCMB survey figures (F4): <https://www.borsagundem.com.tr/yil-sonu-enflasyon-beklentisi-yuzde-3004e-cikti>,
<https://www.hurriyetdailynews.com/turkiyes-year-end-inflation-expectations-edge-up-to-30-percent-229353> (secondary reports of the
November 2026 TCMB Piyasa Katilimcilari Anketi). USD/TRY 43.99 on 2026-03-05: Bigpara TCMB table
(<https://bigpara.hurriyet.com.tr/doviz/merkez-bankasi-doviz-kurlari/5-mart-2026/>).

## 7. Decisions (repo owner, 2026-11-24)

- **F3:** model two marginal bands. Annual consumption up to the threshold (2,920 kWh/year) is priced at the low Retail Tariff,
  only the part above it at the high Retail Tariff. Spec #1 and tickets #8 and #9 were updated to match.
- **F2:** keep the 10 kW default Contracted Power as a marked installer assumption (not a regulatory figure).
- **F4:** escalation rates are real (inflation-adjusted): tariff 2%/year, equipment 0%/year. Lifetime figures are in today's lira.
- **KDV/BTV on the Retail Tariff:** keep 10% KDV and 5% BTV (all-in 3.24 and 4.86 TRY/kWh).

## 8. Remaining open points

1. ~~Confirm the VAT 20% for the PV sale.~~ Done, section 9.1.
2. ~~Confirm the Export Price for a new residential plant.~~ Done, section 9.2 (open sub-points in 9.6).
3. ~~Check the regulation for F1 and F2.~~ Done against the Resmî Gazete texts, section 9.1.
4. Inverter and panel USD prices and BOS/labour/margin are Estimates; the owner may replace them with real price lists
   (`needs-content`).

## 9. Verification: regulation, taxes, Export Price, Discount Rate (ticket #32, 2026-11-25)

**Method.** Primary texts were fetched and read directly: the Resmî Gazete texts of RG 30772 (2019-05-12) and RG 33212
(2026-04-02), the scanned Presidential Decision 7189 (RG 32177, 2023-05-01, read as page images), the mevzuat.gov.tr
consolidated PDFs of Law 5346 and Law 2464 (retrieved 2026-11-25), the EPDK tariff workbook of 2026-04-04 and the Gelir
İdaresi (GİB) KDV rates table (file dated 2025-02-17). "Verified" below means read in one of these. A claim that rests
only on a trade or news site is marked **unverified** and the site is named. The consolidated Lisanssız Elektrik Üretim
Yönetmeliği on mevzuat.gov.tr still does not load, so its article numbers are those of the amendment text. The text of
Presidential Decision 11415 (RG 33279, 2026-06-13) is a scanned image with no text layer and was not read; only its
title and date were checked on the Resmî Gazete index.

### 9.1 Regulation and taxes

| Item | Finding | Source (article, date) | Status |
|---|---|---|---|
| **F1** Monthly Netting | Plants linked to residential (mesken) subscriptions that received a connection call letter on or after 2019-05-12 are netted **monthly**; hourly netting applies to everyone else. | Lisanssız Elektrik Üretim Yönetmeliği Madde 26(20), as replaced by Madde 13 of the amending regulation, RG 33212 of 2026-04-02; in force 2026-05-01 (Madde 26(a) of the amending regulation). Until the market operator's systems existed, Geçici Madde 13 had netting done monthly | **Verified** (full text read) |
| **F2** Contracted Power cap | Installed capacity of a Madde 5(1)(c) plant cannot exceed the contracted power of the linked consumption facility; the facilities' contracted powers may not sum to less than the installed capacity (otherwise the energy is unpaid). No absolute residential kW cap. | Madde 7(10), RG 30772 of 2019-05-12; Madde 28(5) as replaced, RG 33212 of 2026-04-02 | **Verified**. "Installed capacity" is read as the inverter AC capacity: that is the standard reading, the definitions in the text read do not state it (unverified) |
| DC/AC limit | Requested mechanical (DC) capacity cannot exceed **twice** the electrical capacity (wind excepted), so DC/AC up to 2.0 is legal. | Madde 17(7) second sentence, as amended by Madde 8 of the amending regulation, RG 33212 | **Verified** |
| 2x-consumption production cap | Not applied to plants linked to mesken subscriptions. | Madde 26(17) last sentence, RG 33212 | **Verified** |
| Plant category | A rooftop plant that exports is a Madde 5(1)(c) plant (up to 1 MW). A Madde 5(1)(ç) plant (all production used on site, same meter) that still pushes energy to the grid is **not paid** for it (Madde 26(5)). sunquote quotes (c) plants. | Madde 5(1), RG 30772; Madde 26(5), RG 33212 | **Verified** |
| **KDV on residential electricity** | **10%** for mesken and agricultural-irrigation subscriber groups (the general rate is 20%). | Decision 2007/13033 Art. 1(1)(c) and list II item 34. The item was added by CBK 5249 (effective 2022-03-01, at 8%); the list II rate became 10% by CBK 7346 (effective 2023-07-10). GİB table, file dated 2025-02-17 | **Verified** to that date. A 2026 secondary guide (gazelektrik.com) still says 10%. Amendments after 2025-02-17 not checked |
| **BTV** | **5%** of the electricity **sale (energy) price**; the base excludes transmission, distribution and retail-service charges and excludes taxes and funds. (1% applies only to manufacturing-type use.) | Belediye Gelirleri Kanunu 2464 Art. 37 and Art. 38(b) (mevzuat.gov.tr PDF, retrieved 2026-11-25) | **Verified**. That KDV is levied on the sum including BTV (so the formula (1.05 x energy + distribution) x 1.10 is right) is the standard KDV base rule; the KDV Law text was not read (unverified) |
| Enerji Fonu | Whether a fund charge (0.7-1% of the active energy amount, Law 3096) is still on residential bills was not settled: one secondary source says it was removed with the TRT payı, another still lists it. Not modelled. | none primary | **Unverified** (effect on the all-in tariff under 1%) |
| **VAT on a residential PV sale** | **20%**, the general rate. PV modules, inverters and installation appear in neither list I (1%) nor list II (10%) of the decision. Installer-blog claims of a 1% rate or an exemption have no legal text behind them in anything read. | Decision 2007/13033 Art. 1(1)(a), 20% since CBK 7346 (effective 2023-07-10); GİB table, file dated 2025-02-17 | **Verified** by absence from the lists. Confirm with a mali müşavir for a real quote; later amendments not checked |

### 9.2 Export Price (what a new residential plant is paid for surplus)

**Legal chain (verified).**

1. Law 5346 Art. 6/A: a self-consuming unlicensed producer that feeds the grid gets the Annex I prices for **10 years**,
   and the görevli tedarik şirketi (GTŞ) must buy the energy.
2. Annex I item (e): for unlicensed plants that got a call letter on or after 2019-05-10, the price is "the **retail
   single-rate active energy charge of the producer's own subscriber group**, as announced by EPDK in TL kuruş/kWh".
3. Lisanssız Yönetmelik Madde 26(4), (6)(a), (7)(b): the GTŞ buys the surplus left after netting for 10 years from
   connection and pays production x price to the producer by the fifth business day of the month after.
4. The EPDK tariff table valid from 2026-04-04 (Kurul Kararı 14461) gives mesken AG tek terim active energy of
   **49.4065 kr/kWh (up to 8 kWh/day) and 189.5808 kr/kWh (above)**, and a note: for the export-direction distribution
   fee, plants under Annex I item (e) pay **Lisanssız Üretici 2 = 65.6008 kr/kWh**; other unlicensed producers pay
   Üretici 1 = 208.1065 kr/kWh.

**What does not apply.** The YEKDEM unit price of Presidential Decision 7189 (RG 32177, 2023-05-01; solar 106.00 kr/kWh
base, floor 4.95 and ceiling 6.05 US cent/kWh, monthly update by its Annex 2; reported at 292.49 kr/kWh from 2026-11-01 by
enerjiajansi.com.tr quoting EPİAŞ, **unverified**) is for YEK-Belgeli plants. The 2.92 TRY/kWh of the first research
note came from that table, so it was too high for a new residential plant by a factor of about 2.4. Decision 11415
(RG 33279, 2026-06-13: 90% of the YEKDEM price, capped at the hourly PTF) is for plants **after** their 10-year period.
The domestic-equipment bonus (79.49 kr/kWh for 5 years from 2026-11-01, enerjiajansi.com.tr, unverified) needs certified
domestic components; the catalog uses imported Trina and Huawei, so it is not assumed.

**Range and chosen value.**

| Reading | kr/kWh | TRY/kWh | Status |
|---|---|---|---|
| High-tier energy charge, no fee deducted | 189.58 | 1.90 | upper end |
| High-tier energy charge less the Üretici 2 fee (**chosen, lower end**) | 123.98 | **1.24** | components verified; "price less fee" and "high tier" from gesatlasi.com.tr, **unverified** |
| Low-tier energy charge less the Üretici 2 fee | 49.41 - 65.60 | negative | not credible; no source treats it so |
| YEKDEM 7189 solar price | 292.49 | 2.92 | does not apply |

The data file takes the lower end, **1.24 TRY/kWh**, dated 2026-04-04 (the EPDK table it is read from; the price moves
with every EPDK table, so it must be refreshed with the tariff). Two things remain unverified and matter: that the fee is
deducted from the payment, and that the high tier is the one used for mesken (a consumer with no net consumption in the
month would otherwise sit in the low tier). Both come from a single secondary site that cites the EPDK table; the EPDK
note itself only says which distribution tariff applies.

**Surplus treatment (verified).** Madde 26 as amended has no carry-over (devir) of unused surplus to a later month or
year; the surplus left after the monthly netting is paid in the month it arises. **This agrees with ADR 0005** (surplus
sold at the Export Price in its month), so nothing is raised against it.

**Not modelled, for the owner.**

- The purchase guarantee is 10 years (Madde 26(4)); the Quote horizon is 25 years. After year 10 the surplus falls under
  rules like Decision 11415 (90% of the YEKDEM price, capped at the PTF) and the distribution-fee tariff changes. The
  Export Price is applied for the whole lifetime. It only prices the surplus share of the savings, and the lower end is
  used, so the error is small but not zero.
- Income tax or KDV on the sale of surplus by an individual (e-müstahsil practice) was not researched.

### 9.3 Discount Rate (added to `assumptions.toml` by ticket #34)

| Field | Value |
|---|---|
| Name | `discount_rate_real` |
| **Value** | **0.056** (5.6% a year, real) |
| Kind | derived (a rounded auction yield; the choice of instrument is a judgment) |
| Source | Real compound yield **5.61%** at the Treasury auction of the 4-year CPI-linked bond TRT080530T27 (2.63% real coupon), reported 2026-06-08 by Bloomberg HT (https://www.bloomberght.com/hazine-4-yil-vadeli-tufe-endeksli-tahvilde-13-2-milyar-tl-borclandi-3779359). A 5-year CPI-linked auction earlier in 2026 was reported at 5.37% on average (4.89-5.56%). **Unverified against hmb.gov.tr** (secondary reporting); no CPI-linked auction in November 2026 was found. |
| Date | 2026-06-08 |

Why this rate: the cash flow is in today's lira (ADR 0003), so the rate must be real (ADR 0006). The riskless real
alternative for a household is a CPI-indexed Treasury bond, the cleanest benchmark. Cross-check from the other side: the
policy rate of 36% (TCMB, cut by 100 bp on 2026-10-22) against the 24.04% 12-month-ahead CPI expectation (TCMB Market
Participants Survey, November 2026, secondary reports) is about 9.6% real, an upper bound for a short-term deposit. A
higher rate lowers the NPV. 5.6% is the recommendation; the repo owner may prefer the deposit-based figure for a more
conservative NPV.

### 9.4 Data file changes

| File and field | Before | After |
|---|---|---|
| `tariff.toml` `export_price_try_per_kwh` | 2.92, estimate, 2026-11-01 | **1.24**, derived, 2026-04-04, range and source in the source text |
| `tariff.toml` `[tariff]` source, low and high tariff source text | BTV and KDV "not confirmed" | verified against Law 2464 and Decision 2007/13033 |
| `assumptions.toml` `discount_rate_real` | absent | **0.056**, derived, 2026-06-08 (added by ticket #34) |
| `assumptions.toml` `vat_rate` | 0.20, estimate | 0.20, **direct**, source text with the article and the caveat |
| `assumptions.toml` `default_contracted_power_kw.residential` | source text only | cap citations added (value stays 10, estimate) |
| `assumptions.toml` `dc_ac_ratio_max` | source text only | legal 2.0 ceiling cited (value stays 1.50, estimate) |

Tests that asserted the old Export Price (`tests/adapters/test_data_files.py`, `tests/test_wiring.py`) were updated.

### 9.5 Choices made without asking

- Export Price: the lower end, 1.24 (the ticket's rule), instead of the 1.90 gross price.
- Discount Rate: the real CPI-linked bond yield, not a deposit-based or risk-adjusted rate.
- VAT kind set to `direct` for the rate, with its applicability to a PV sale verified by absence from the rate lists.
- No comment raised on #30: surplus is not carried over, so ADR 0005 stands.

### 9.6 Still open

1. Confirm in the EPDK decision text (not the table) that the export-direction fee is deducted from the surplus payment
   and which mesken tier is used. This is the single unverified assumption behind 1.24.
2. Read Decision 11415 and Presidential Decision 7189 as text (scanned images here) if the 10-year horizon matters.
3. Refresh the tariff and the Export Price together when EPDK publishes a table after 2026-04-04.
4. Enerji Fonu, KDV on the sale of surplus, and KDV amendments after 2025-02-17.
5. The mesken SKTT limit (4,000 kWh/year in 2026; one secondary site reports 3,000 kWh for 2027) is a separate rule from
   the Tariff Tier.
