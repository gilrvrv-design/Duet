# Piano LED rail: sourcing and product research

Checked **2026-11-28**. Prices, tariffs and stock change. Every figure below is sourced in the files listed at the end, and anything not confirmed is marked **unverified**. Nobody was contacted, no accounts were created, no forms were submitted and nothing was bought.

---

## The three decisions to make next

**1. Lock the rail as two pieces (about 2 × 625 mm), not one 1.25 m piece.** *Recommended: two pieces.*
- A box of about 130 cm is longer than 48 in, so UPS and FedEx add an *Additional Handling* surcharge. UPS's 2026 guide seems to bill those parcels at a 40 lb minimum weight.
- No low-minimum box printer makes a box that long: Packlane stops at 31 in.
- No supplier sells a 1.25 m reel of 144/m strip, so the strip is cut either way.
- Two halves fit a printed 26 × 4 × 3 in box (Packlane, $3.88 at 100 units, $2.74 at 500).
- Two halves also fit 3D printers. JLC3DP's resin printers take 780 mm parts.
- The cost is a joint: a connector between the two strip halves and a joiner in the rail.

**2. Choose the price, the sales channel and the cost target together, because the brief's numbers do not fit yet.**
- With the cheapest listed parts at 500 units, landed cost is **$57.90**. Of that, $14.59 is duty at 41.4%, $7.16 is air freight and $30.49 is parts.
- At **$79 retail** that leaves 27% gross margin, and **12% after a 15% Amazon referral fee**. Amazon fulfilment fees aren't counted yet.
- Pick one or more of these:
  - (a) Sell mainly on your own site.
  - (b) Price at about $99. Margin after Amazon's fee is 26% at 500 units, still before fulfilment.
  - (c) Bring the ex-factory cost down to about **$28** (for 40% gross margin selling direct at $79) or about **$19** (for 40% on Amazon at $79). It is now $35.23.
- Every $1 off the factory price saves $1.41 landed, because duty is charged on it.

**3. Decide where the controller comes from.**
- **Off-the-shelf board, re-flashed with your firmware:** fastest, $15–25 each, with USB-C, I2S mic and level shifter already on board. Candidates:
  - QuinLED Dig2Go, $24.99
  - SMARTLIGHT SLWF-03, $14.99 at 10+
- **Your own ESP32-S3 board, built by Seeed Fusion, PCBWay or JLCPCB:** probably the only way to reach option (c) in decision 2. It costs a design cycle and an FCC Part 15B test of your own board.
- **Both paths need:**
  - a Part 15B test of the finished product;
  - a US responsible party: you.
- **Suggestion:** make the first 50–100 units on off-the-shelf boards. Get a custom-board quote in parallel for the 500-unit batch.

Two more items need an answer before launch, though they aren't design choices:
- **Children.** Will you market it to children? If so, you need a CPSC children's product certificate and third-party testing.
- **Radio exposure.** The ESP32 module's FCC grant assumes the antenna stays at least 20 cm from people. A player's hands may come closer than that to the end cap, so ask your test lab.

---

## Recommended plan

**Stage 0: samples and prototype (now, a few hundred dollars).**
- Order one of each:
  - BTF 2 m reel, $29.50
  - Ledworker strip sample, $50
  - Dig2Go, $24.99
  - SLWF-03, $15.99
  - GLEDOPTO GL-C-015WL-D, $22.98
  - SuperLightingLED HL-BAPL004 channel with black diffuser, $9.99
  - SiDaWang black channel sample, $5
- Print end caps and a joiner at JLC3DP. Build 3–5 units.
- Measure these, because the model now guesses them:
  - real current draw at your brightness cap;
  - packed weight;
  - whether the strip fits a 10 mm or a 12 mm channel.
- **Power is the main engineering limit.** 180 LEDs at full white draw about 6.6 A by the WS2812B datasheet, or about 10.8 A by Adafruit's 60 mA rule. A USB-C phone charger gives at most 3 A at 5 V.
  - So cap brightness at roughly a quarter to a third of full white.
  - Read the charger's advertised current (5.1 kΩ pull-downs on the CC pins) and limit to it.
  - Add a fuse or PTC.

**Stage 1: first 50–100 units.**
- Send the drafts in `outreach/`.
- Build:
  - two-piece rail, black-diffuser aluminum profile cut to 625 mm;
  - printed end caps;
  - off-the-shelf controller re-flashed with your firmware;
  - Packlane 26 × 4 × 3 in printed box.
- Flash and kit them yourself, or have Seeed Fusion do it. Seeed is the only partner whose public pages cover building the board, flashing, kitting, packaging and fulfilment together.
- In parallel:
  - FCC Part 15B test (Supplier's Declaration of Conformity) at an ISO 17025 lab that is not owned or controlled by a "prohibited entity";
  - "Contains FCC ID" label;
  - manual statements;
  - "Made in China" marking;
  - US trademark filing, needed for Amazon Brand Registry.
- Bring the first batch in by air.

**Stage 2: 500+ units.**
- Get all-in quotes (parts, flashing, assembly, branded box) from Seeed Fusion, PCBWay and Elecrow.
- Move the end cap to an aluminum injection mould: Protolabs publishes "from about $1,500".
- Get a quote for your own controller board.
- Ship by sea: Asia to US West Coast is about $7,500 per 40 ft container (Freightos, 25 Nov 2026). Price your 2.6 m³ partial-container load with a freight forwarder.
- Get a CBP binding ruling on the HTS code before you place the order.

**Stage 3: 1,000+ units.**
- A custom aluminum extrusion with diffuser groove, joiner channel and soft feet built in. The die costs about $400–4,000; minimum order about 1,000–2,000 lb per shape.
- An injection-moulded end cap.

---

## 1. Competitors (`competitors.csv`, 17 entries)

| Product | Price | Needs MIDI/USB | Acoustic piano | Mounting |
|---|---|---|---|---|
| Piano LED Plus (France) | €169–239, plus €99/yr after year 1; no USD price shown | Yes | No (stated) | Adhesive strip, magnetic box |
| The ONE Piano Hi-Lite | $269.99 MSRP; appears discontinued (unverified) | No (phone app) | Yes, claimed | Rests on keys, 88-key only |
| KEEZI | $149.99, sold out | Mostly | Lights only, no note detection | "Mounting kit" (type unverified) |
| i-Piano (Etsy) | $149–169 (snippet) | Yes | No | Built for each piano |
| Pianethor (open source, AGPL, Apr 2026) | Parts only | **No: ESP32 access point, MIDI file upload** | Yes, mic volume threshold only | Adhesive strap |
| onlaj Piano LED Visualizer, PianoLights, PianoLux and others | $40–100 in parts | Yes | No | Tape / channel |

**What buyers complain about:**
- LEDs don't line up with the keys, and the strip is the wrong length for some pianos.
- They have to re-pair or set up on every use.
- Buggy apps and subscription paywalls.
- Magnets that don't hold.
- Blue LEDs too dim in daylight.
- Support only in French, and costly returns.

Sources: Piano LED Plus's own product reviews, Trustpilot (4.3 from 258 reviews) and the App Store. Amazon and Reddit couldn't be read (blocked), so those complaints are missing.

**What it means:**
- At $60–80 you would be about half the price of every commercial strip.
- No commercial product you can buy today works on acoustic pianos with note detection. That gap is your position.
- The basic design already exists as a hobby project (Pianethor), so you have to win on finish, mounting, easy key alignment and real pitch detection.
- **US Patent 11,087,636** describes a microphone that waits for the right note before moving on. I couldn't open it to see who owns it or what it claims. **Have a patent attorney check freedom to operate before shipping mic-based "wait for note".**

## 2. Components (`suppliers.csv`: 7 strip, 8 controller, 8 channel suppliers)

**LED strip.**
- BTF-LIGHTING official store:
  - 1 m reel $15.99, 2 m reel $29.50.
  - 20–25% off at 50–149 pieces, 25–30% off at 150+.
  - 144/m comes only in 1 m and 2 m reels.
- Ledworker on Alibaba: $2.50–12.33 per metre, 5 m minimum. A 5 m reel makes exactly four units.
- Adafruit: $59.95, or $47.96 at 100+. It may ship SK6812 chips instead.
- DigiKey has a Seeed WS2813B strip at $22.45.
- SparkFun's strip is retired.

**Controllers (ESP32, I2S mic, USB-C).**

| Board | Price | Notes |
|---|---|---|
| QuinLED Dig2Go | $24.99 | ICS-43434 mic, level shifter, USB-C 5 V/3 A |
| Adafruit Sparkle Motion | $24.95; $19.96 at 100+ | Out of stock |
| GLEDOPTO GL-C-015WL-D | $22.98; $19.53 at 100+ | Mic model and USB type not stated |
| RevK board | $22.31 | ESP32-S3, no level shifter |
| SMARTLIGHT SLWF-03 | $14.99 at 10+ | |
| Athom | $23.80 | |
| XIAO ESP32-S3 Sense | $18.90 | Bare board |
| M5Stack Atom Voice | $12.15 | PDM mic |

**Channels with black diffuser.**
- SuperLightingLED HL-BAPL004: $9.99 per 1 m, 12.2 mm inside.
- SiDaWang on Alibaba: $2.00/m, cuts to length.
- Muzata smoky 6-pack.
- KLUS (no smoked lens).
- DigiKey JKL ZFC-11: the only listing with full price breaks, $22.72 / $15.40 at 100 / $14.23 at 500. Its diffuser colour isn't stated.

**Price breaks at 100 and 500 units were published by only a few suppliers.** The rest are marked "unverified – request quote".

## 3. Assembly partners (`suppliers.csv`, 11 entries)

| Partner | Board assembly | Firmware flashing | Box build / kitting | Packaging | Fulfilment | Stated minimum |
|---|---|---|---|---|---|---|
| **Seeed Fusion** | Yes | Yes (custom firmware "case by case") | Kitting | Yes | Yes | Boards 1 pc; kits 5 (secondary) |
| PCBWay | Yes | Yes | Yes | Yes | — | Boards 5 pcs |
| Elecrow | Yes | Yes | Yes | Yes | — | Not stated |
| JLCPCB | Yes | $7.86 + $7.86/h, own boards only | No | Static bag | No | — |
| NextPCB | Yes, no minimum | Yes | Kitting per a secondary source | — | — | None |
| MacroFab (US) | Yes | Yes | Yes | — | Per snippet | None |
| CircuitHub (US) | Yes | Only over 200 units | No | No | No | 200 |
| Bittele/7pcb | Yes | Yes | Per snippet | — | No | 25 |
| DCL (US warehouse) | No | Re-flashes | Yes | Sourcing | Yes | Not stated |
| Fulfillrite (US warehouse) | No | — | Yes | Yes | Yes | $399/month |

Tempo Automation is defunct (liquidated December 2023). None of these publish box-build prices, so the cost model uses a placeholder.

## 4. Housing

| Volume | Rail | End cap |
|---|---|---|
| Under 50 | Stock black aluminum channel (Klus, Muzata, SuperLightingLED), about $8–14/m retail | JLC3DP nylon (MJF) at $0.275/g published, about $3–5 per cap (estimate) |
| 50–500 | Alibaba stock profile cut to 2 × 625 mm and anodised, about $1.4–5/m listed (minimum about 100–500 m) | Printed up to about 200 units. Above that, Protolabs aluminum mould from about $1,500 (published) |
| 1,000+ | Custom extrusion: die $400–2,000 (Gabrian) or $1,000–4,000 (industry body); minimum about 1,000–2,000 lb per shape | Aluminum or P20 steel mould, about $1,500–12,000 (published plus third-party) |

**No instant quotes were possible.** Every service needs a CAD upload or an account. Full table: `research-notes/housing.md`.

## 5. Packaging (`suppliers.csv`, 9 entries)

| Box | 50 units | 100 units | 500 units |
|---|---|---|---|
| **Packlane printed 26 × 4 × 3 in (two-piece rail)** | $4.88 | $3.88 | $2.74 |
| Packlane printed 14 × 8 × 2.5 in shipper | $5.12 | $4.11 | $2.93 |
| Packlane mailer 14 × 8 × 2.5 in | $5.49 | $4.49 | $3.25 |
| EcoEnclose 14 × 8 × 5 in unbranded (plates $95–800 extra; branded minimum 100) | $2.47 | $2.47 | $2.14 |
| Uline 4 × 4 × 60 in, unprinted (fits a one-piece rail; add a sticker) | $3.53 (25 tier) | $3.32 | $2.67 |
| Alibaba long box | below minimum | below minimum | quote needed (minimum 500) |

- Arka, Refine (100 minimum), Salazar and The Custom Boxes all need a quote.
- Pakible may have closed.

## 6. Compliance and import (`research-notes/compliance.md` has the full citations)

**FCC.**
- The pre-certified module covers the radio:
  - ESP32-WROOM-32E: FCC ID 2AC7Z-ESP32WROOM32E
  - ESP32-S3-WROOM-1: 2AC7Z-ESPS3WROOM1
- The finished product still needs:
  - a **"Contains FCC ID: …" label** (47 CFR 15.212);
  - a **Part 15 Subpart B Class B test under a Supplier's Declaration of Conformity** (15.101, 2.906);
  - a compliance statement naming a **US responsible party** (2.1077);
  - the manual statements in 15.19, 15.21 and 15.105(b);
  - records kept under 2.938.
- **Chinese test labs:** testing is allowed today as long as the lab isn't owned or controlled by a prohibited entity (2.906(a)(1)).
  - From 1 Dec 2028, FCC order 26-73 stops recognising labs in mainland China. It says SDoC rules are unchanged, but it keeps open a proposal to require US or "reciprocal" labs for SDoC too.
  - A US, EU, Taiwan, Japan or Korea lab protects the report's long-term value.
- **Test cost: unverified.**

**Power adapter.**
- Not bundling one (recommended): you have no Department of Energy duties, but state "5 V ⎓ 3 A USB-C, listed adapter".
- Bundling one makes you its importer. It then needs:
  - DOE Level VI efficiency and the "VI" mark (10 CFR 430.32(w));
  - DOE certification;
  - a California database listing (unverified);
  - in practice, a UL/IEC 62368-1 listing.

**Other rules.**
- "Made in China" on the device and the box (19 CFR 134.11).
- Probably no CPSC General Certificate of Conformity for an adult product.
- **Marketing to children brings in** third-party testing, a children's product certificate, lead limits, tracking labels and children's privacy rules.
- Prop 65: unverified, so ask an attorney.

**Amazon.**
- The listing must carry FCC authorisation details and a US responsible party (Amazon's radio-device policy).
- Expect requests for an FCC report and an ISO 17025 safety report.
- Brand Registry needs a registered or pending trademark.
- No battery means no dangerous-goods review.

**Tariff (estimate; confirm with a licensed customs broker).**
- **HTS 9405.42.8440** (LED lighting), if sold as a kit. The rates stack:
  - general duty 3.9%
  - Section 301 List 3: 25%
  - Section 301 forced-labour action from 24 Jul 2026: 12.5%
  - **Total about 41.4%.**
- Fees: Merchandise Processing Fee 0.3464% (minimum about $34.58 per entry); Harbor Maintenance Fee 0.125% by sea only.
- Gone: the IEEPA "fentanyl" and "reciprocal" tariffs. The Supreme Court ruled them invalid and CBP stopped collecting on 24 Feb 2026 (secondary sources). The temporary Section 122 surcharge expired on 23 Jul 2026.
- Duty-free entry under $800 is still suspended.
- **Watch:** an "excess capacity" Section 301 tariff proposed on 25 Nov 2026 could raise the total to about 49%. Comments are due 5 Jan 2027.

**Confirm with a professional:**
- **Customs broker:** HTS code and binding ruling; the duty stack on the day of entry; CPSC eFiling.
- **FCC test lab:** test scope; the 20 cm exposure condition; lab ownership; label text; re-test after adding the microphone.
- **Attorney:** children's product decision; Prop 65; trademark; patent 11,087,636; a privacy policy once the microphone exists.

## 7. Cost model (`costs.xlsx`)

The model has two price levels at each volume:
- **High:** page-verified distributor and retail prices for parts that meet the spec.
- **Low:** the cheapest factory and marketplace listings found.

Real quotes should land between them. Yellow cells are assumptions with no supplier price behind them; replace them with quotes. They account for $10.68–17.38 per unit before duty, depending on the column.

| Per unit, USD | High @100 | High @500 | Low @100 | Low @500 |
|---|---|---|---|---|
| Parts cost | 71.08 | 70.09 | **30.49** | **30.49** |
| Parts cost vs $35 target | +36.08 | +35.09 | −4.51 | −4.51 |
| Box + assembly | 8.88 | 6.74 | 6.88 | 4.74 |
| Ex-factory value | 79.96 | 76.83 | 37.37 | 35.23 |
| Air freight (0.85 kg chargeable × $8.40/kg) | 7.16 | 7.16 | 7.16 | 7.16 |
| Forwarder fees (assumed $400 per shipment) | 4.00 | 0.80 | 4.00 | 0.80 |
| Duty at 41.4% plus processing fee | 33.45 | 32.08 | 15.82 | 14.71 |
| **Landed cost** | **124.56** | **116.87** | **64.34** | **57.90** |

| Retail price | Gross margin, Low @500 | After 15% Amazon fee, Low @500 |
|---|---|---|
| $59 | $1.11 (1.9%) | −$7.75 |
| $69 | $11.11 (16.1%) | $0.76 (1.1%) |
| $79 | $21.11 (26.7%) | $9.26 (11.7%) |
| $89 | $31.11 (34.9%) | $17.76 (19.9%) |
| $99 | $41.11 (41.5%) | $26.26 (26.5%) |

**What the model says:**
- The **$35 parts target is reachable only at factory prices** (Low: $30.49).
- **Landed cost is the real problem.** Duty adds about 41% on top of the factory price, and air freight about $7.
- The High column is a ceiling rather than a real plan. Buying retail parts and then paying import duty again on them double-counts.

**Biggest costs that can still come down:**
1. Controller, $15–25. Your own board is the lever.
2. Printed parts, about $6.88, an estimate. An injection mould can cut this at 500+ units.
3. Air freight, $7.16. Sea freight at 500 units.
4. Duty, about 41% of the factory price. The only legal levers are classification, a binding ruling, first-sale valuation and exclusions. **Ask a customs broker; don't move assembly just for tariff reasons without legal advice.**

**Fulfilment and shipping to customers were not researched.** They are an input on the `Margin` sheet, set to $0, which flatters every margin figure.

**The arithmetic was re-checked.** All 178 formulas recalculated in LibreOffice with no errors. Every line also matched a separate Python calculation of the same inputs.

## 8. Outreach drafts (`outreach/`)

Six messages:
- LED strip makers
- ESP32 controller makers
- LED channel makers
- assembly partners
- housing (printing, extrusion, moulding)
- packaging

Each asks for:
- prices at 100, 500 and 1,000 units, both factory price (EXW/FOB) and delivered duty-paid to the US (DDP);
- minimum order, sample cost and lead time;
- firmware flashing and packaging services;
- FCC and test documents.

---

## What I couldn't find or verify

- **Quotes:** price breaks at 100 and 500 units for most suppliers. No supplier publishes box-build, kitting or flashing prices. There were no instant quotes for 3D printing, CNC or moulding, since all need a CAD upload or an account.
- **Custom firmware:** whether GLEDOPTO, Athom or the Alibaba controller makers will flash your firmware and private-label the board.
- **Strip details:** a 1.25 m reel (none exists); the BTF strip's width; the mic model on Sparkle Motion and GLEDOPTO.
- **Freight:** a China-specific air rate (the Freightos figure covers all of the Far East); partial-container sea rates; forwarder fees; UPS/FedEx surcharge amounts (their pages blocked automated access).
- **Tests:** costs of FCC Part 15B and safety testing.
- **Official FCC pages:** the module integration and e-label guidance (KDB 996369 and 784748) and the FCC Covered List page (apps.fcc.gov blocked). Covered here from secondary sources.
- **Other regulators and Amazon:** Amazon's official pages on electronics compliance, GTIN exemptions and FBA prep (login required); CPSC lead and tracking-label pages; Prop 65.
- **Tariff details:** the final rate of the proposed excess-capacity tariff; the Supreme Court and CBP texts on the end of the IEEPA tariffs (secondary sources only); the FY2027 processing-fee minimum and maximum (secondary).
- **Competitor gaps:** Amazon and Reddit reviews (blocked); Piano LED Plus's USD price; whether the Hi-Lite is still sold; who owns patent 11,087,636 and what it claims.
- **Fulfilment:** Amazon FBA fees, Amazon referral fees for this category (15% is an assumption), and 3PL pick-pack fees.

## Files

| File | What it holds |
|---|---|
| `report.md` | This summary |
| `competitors.csv` | 17 competing products and projects, with sources |
| `suppliers.csv` | 49 suppliers (strip, controller, channel, assembly, packaging, housing) with prices, minimums, contacts, verification level and the 2026-11-28 link check |
| `costs.xlsx` | Landed cost and margin model. Sheets: Read me, Inputs, Landed cost, Margin, One-off costs, Sources |
| `outreach/` | Six ready-to-send inquiry drafts plus tips |
| `sources.md` | Every URL used, whether it opened, and the supplier link-check results |
| `research-notes/` | Full research notes behind each section, with per-fact citations |
