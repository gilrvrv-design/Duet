# US Compliance and Import Research: ESP32 Wi-Fi LED Controller (made in China, sold in the US)

**Date checked:** 2026-11-28. This is research, not legal, customs or regulatory advice. Every item marked **[CONFIRM]** should be checked with the named professional before you rely on it.

**Product assumed:** an ESP32-based Wi-Fi controller using a pre-certified Espressif module (ESP32-WROOM-32E or ESP32-S3-WROOM-1). It drives a 5 V WS2812B addressable LED strip, which may or may not be sold in the same box. Power comes over USB-C from the user's own adapter, with an adapter bundled as an option. There is no battery. An I2S microphone may be added later. The goods are made in China, imported by a US entity, and sold through the founder's own website and Amazon US.

**Sourcing levels used below:**
- **Verified (primary):** I opened the official page or file and read the text.
- **Secondary:** a law firm, broker or news summary. I could not open the official text.
- **Unverified:** I could not confirm it.

---

## 0. Key findings

1. **Wi-Fi radio (FCC).** Using Espressif's single-modular grant covers the module's transmitter. Both module grants are verified:
   - FCC ID 2AC7Z-ESP32WROOM32E, granted 04/10/2020.
   - FCC ID 2AC7Z-ESPS3WROOM1, granted 01/21/2022.

   The finished product still needs:
   - a "Contains FCC ID: …" label;
   - Part 15 Subpart B (Class B digital device) authorization by SDoC, which means testing, records, a US responsible party and user-manual statements;
   - an integration check under KDB 996369.
2. **Chinese test labs (FCC).**
   - Today, SDoC testing does **not** require an FCC-recognized lab. However, it must not be done at a lab owned or controlled by a "prohibited entity" (47 CFR 2.906(a)(1), verified).
   - The FCC's Oct 29, 2026 order (FCC 26-73) stops recognizing labs in mainland China and other non-reciprocal economies from **Dec 1, 2028**. It expressly "does not change existing SDoC eligibility rules." It does keep open a proposal that SDoC testing must be done in the US or a reciprocal economy (verified).
3. **Tariffs (best estimate).** HTS **9405.42.8440**, an LED luminaire or lighting product. Rates shown are added on top of the value of the goods.

   | Component | Rate |
   |---|---|
   | General (MFN) duty | 3.9% |
   | Section 301 China, List 3 | 25% |
   | Section 301 "forced-labor" action on China (effective Jul 24, 2026) | 12.5% |
   | **Duty subtotal** | **≈ 41.4%** |
   | Merchandise Processing Fee (MPF) | 0.3464% (minimum and maximum apply) |
   | Harbor Maintenance Fee (HMF), ocean freight only | 0.125% |
   | **All-in** | **≈ 41.9%** |

   - The IEEPA "fentanyl" and "reciprocal" tariffs are gone. The Supreme Court ruled on Feb 20, 2026, and CBP stopped collecting on Feb 24, 2026.
   - The Section 122 10% surcharge that replaced them expired at the close of Jul 23, 2026.
   - A **proposed** new Section 301 "excess capacity" tariff, announced Nov 25, 2026, could add more. **[CONFIRM with a licensed customs broker; get a binding ruling.]**
4. **Amazon.**
   - The listing must carry FCC authorization data (Amazon's RF device policy).
   - Expect Amazon to request safety and compliance documents.
   - Brand Registry needs a pending or registered trademark.
   - With no battery, the battery and dangerous-goods rules for Fulfillment by Amazon (FBA) are avoided.
5. **Consumer safety (CPSC).** Probably no Consumer Product Safety Commission (CPSC) rule applies to a general-use USB LED controller, so a General Certificate of Conformity (GCC) is probably not required. Marketing to children (12 and under) changes this sharply. **[DECISION + CONFIRM with an attorney.]**

---

## 1. FCC

### 1.1 Module (intentional radiator): what the pre-certified module covers

- **47 CFR 15.212 (Modular transmitters), verified on eCFR (current to 2026-11-25).**
  - A single modular transmitter is a "completely self-contained radiofrequency transmitter device that is typically incorporated into another product."
  - If the module's FCC ID is not visible once installed, "the outside of the device into which the module is installed must also display a label referring to the enclosed module." Suggested wording: **"Contains Transmitter Module FCC ID: XYZMODEL1" or "Contains FCC ID: XYZMODEL1."**
- **ESP32-WROOM-32E grant, verified (PDF hosted by Espressif).**

  | Field | Value |
  |---|---|
  | FCC ID | **2AC7Z-ESP32WROOM32E** |
  | Grantee | Espressif Systems (Shanghai) Co., Ltd |
  | Grant date | 04/10/2020, by Bay Area Compliance Laboratory Corp. (TCB) |
  | Equipment class | DTS |
  | Rule parts | 15C, 2412–2462 MHz (0.398 W conducted) and 2402–2480 MHz |
  | Modular type | Single Modular |

  Grant conditions:
  - "approved for use in **mobile** RF exposure category configurations … separation distance of at least **20 cm** from all persons."
  - "Installation of this device into **portable** RF Exposure category host devices requires the submission of a Class II permissive change or new application."
  - Co-location with other simultaneously operating transmitters must be evaluated.
  - There is also a separate DSS (Bluetooth Classic) grant. Espressif's certificates page lists both "FCC DSS" and "FCC DTS" for WROOM-32E, issued 2020.04.17.
- **ESP32-S3-WROOM-1 grant, verified (PDF hosted by Espressif).**

  | Field | Value |
  |---|---|
  | FCC ID | **2AC7Z-ESPS3WROOM1** |
  | Grant date | 01/21/2022, by Nemko North America (TCB) |
  | Equipment class | DTS |
  | Rule parts | 15C, 2412–2462 MHz (0.3597 W) and 2402–2480 MHz (0.0109 W) |
  | Modular type | Single Modular |

  Grant note: "The integrator installing this module into their product must ensure that the final composite product complies with the FCC requirements by a technical assessment or evaluation to the FCC rules, including the transmitter operation and should refer to guidance in **KDB 996369**. Separate approval is required for all other operating configurations, including portable configurations with respect to 2.1093 and different antenna configurations."

**What this means for you.**
- An LED controller that sits on a shelf or wall, more than 20 cm from people, fits the "mobile" condition.
- Keep the module's own antenna. That means the PCB antenna on WROOM-32E or WROOM-1. The -U variants use an external antenna, which must be a type listed in the grant.
- Follow Espressif's layout keep-out guidance for the antenna.
- Do not change the RF firmware parameters beyond what Espressif allows.
- A wearable or handheld design within 20 cm would need a permissive change or a new grant. **[CONFIRM with an FCC test lab/TCB.]**

**KDB 996369 (module integration guidance; D04 is the host-manufacturer guide).** I could **not** open it: apps.fcc.gov KDB pages returned "Access Denied" to this tool. Secondary sources (Element, Bureau Veritas, Nemko; see the URL list) say D04 tells host makers to:
- confirm the host uses the module within its grant conditions;
- do a host-level check of radiated spurious emissions with the module transmitting, often a short "spot check" by a lab;
- authorize the host's own digital circuitry under Part 15 Subpart B.

Treat this as secondary. **[CONFIRM the current D04 version and the required testing scope with the test lab.]**

### 1.2 The host product: Part 15 Subpart B, SDoC, records and labels

- **47 CFR 15.101(a), verified.** "unintentional radiators shall be authorized prior to the initiation of marketing, pursuant to the procedures for certification or Supplier's Declaration of Conformity (SDoC)…" Table: "Other Class B digital devices & peripherals: SDoC or Certification."
  - The ESP32 host is a digital device using clocks above 9 kHz, so it is a Class B digital device in a residential setting.
  - The module grant does not cover the host's digital emissions.
  - The WS2812B data line and the LED strip wiring can radiate. Test with the strip attached in its typical (worst-case) length.
- **47 CFR 2.906, SDoC, verified.**
  - The responsible party "makes measurements or completes other procedures … to ensure that the equipment complies."
  - **(a)(1):** "Equipment testing … must not be performed at a measurement facility that is owned by, controlled by, or under the direction of a prohibited entity, as defined in § 2.902."
  - (a)(2): no filing with the FCC unless requested.
  - **(d):** equipment produced by an entity on the **Covered List** cannot use SDoC.
  - Espressif does not appear on the Covered List in anything I found. However, I could not open fcc.gov/supplychain/coveredlist (403), so this is **unverified**. 2026 additions found in secondary results include foreign-produced routers (Mar 2026), drones, "advanced robotic devices" and power inverters (Jul 2026). Your product is none of these, unless it is marketed as a router.
- **47 CFR 2.1077, compliance information, verified.**
  - An SDoC product must ship with a compliance information statement: product name and model; the 15.19(a)(3) statement; and the US responsible party's name, address and phone or internet contact.
  - **"The responsible party for Supplier's Declaration of Conformity must be located within the United States."**
  - Under 2.1077(b), for products assembled from modular components, the statement identifies the modules, including the module's FCC ID.
  - It may go in the manual or on a separate sheet. An electronic version is allowed per 2.935.
- **47 CFR 2.938, record retention, verified.** The responsible party keeps design drawings, production inspection procedures and test results. For SDoC this includes: test dates, the name of the lab, test methods, equipment under test and support equipment, cable arrangements, and photos of the test setup. Note: eCFR flags an amendment published at 90 FR 38067 (Aug 7, 2025).
- **47 CFR 15.19(a)(3), label, verified.** "This device complies with part 15 of the FCC Rules. Operation is subject to the following two conditions: (1) This device may not cause harmful interference, and (2) this device must accept any interference received, including interference that may cause undesired operation."
  - Under 15.19(a)(5), if the device is too small for 4-point text **and has no display**, the statement can go in the manual plus on the packaging or a removable label.
- **47 CFR 15.21, verified.** The manual must warn that "changes or modifications not expressly approved by the party responsible for compliance could void the user's authority to operate the equipment." An electronic manual is OK if users can be expected to access it.
- **47 CFR 15.105(b), verified.** Class B devices must include the standard text in the manual: "This equipment has been tested and found to comply with the limits for a Class B digital device, pursuant to part 15 of the FCC Rules…", followed by the list of remedies (reorient the antenna, increase separation, etc.).
- **E-labelling (KDB 784748, and 47 CFR 2.935).**
  - I could **not** open KDB 784748 (apps.fcc.gov blocked).
  - Secondary sources say e-labels under KDB 784748 D02 apply to devices **with an integrated display**.
  - An LED controller without a screen should use a **physical label**. The web UI showing the FCC info is generally not enough. **[CONFIRM with the lab/TCB.]**
- **Covered List / SDoC exclusion.** See 2.906(d) above. Also check that your contract manufacturer is not a Covered List entity.

### 1.3 FCC rules on labs and TCBs in "foreign adversary" and non-reciprocal countries (status 2026-11-28)

- **2025 "Bad Labs" rules (in effect).**
  - The FCC prohibits recognizing test labs and TCBs "owned by, or subject to the direction or control of, a foreign adversary country." Source: FCC news release, Jun 9, 2026 (DOC-422289A1), verified.
  - That release says 23 labs had been denied or had recognition withdrawn. The Oct 29, 2026 release says **29** labs lost recognition.
  - For SDoC, the matching rule is 2.906(a)(1) above (verified): **you may not use a lab owned or controlled by a prohibited entity, even for SDoC.**
- **FCC 26-73, Third Report and Order and Third FNPRM, adopted Oct 29, 2026 (ET Docket 24-136), verified (order text and press release).**
  - The FCC limits recognition of test labs to those located in the US or "Reciprocal Economies," effective **December 1, 2028**, after about a 24-month transition. Between Dec 1, 2026 and Dec 1, 2028 the FCC will keep granting non-reciprocal labs only shortened recognition.
  - Mainland China is a non-reciprocal economy.
  - The order states: "For equipment authorized using the Supplier's Declaration of Conformity (SDoC) procedure, the Commission does not require testing performed at an FCC-recognized accredited testing laboratory. See 47 CFR § 2.906."
  - It also states: "We confirm that today's action does not change existing SDoC eligibility rules or fees."
  - The FNPRM keeps the record open on "whether equipment authorized through the SDoC process should be tested in laboratories based in the U.S. or Reciprocal Economies."
- **What this means for you.**
  - Today, SDoC Part 15B testing at a Chinese lab is permitted, **provided** the lab is not owned or controlled by a prohibited entity.
  - Ask the lab for an ownership statement. Prefer an ISO/IEC 17025-accredited lab.
  - Because the SDoC rule may tighten, and because Amazon often asks for ISO 17025 reports, consider a lab in the US or a reciprocal economy (Taiwan, EU, Japan, Korea and others; Appendix D of FCC 26-73 lists 62 reciprocal economies, per a secondary source) or a US-recognized lab. That protects the test report's usefulness.
  - **[CONFIRM the lab's ownership status and the final rules with the lab/TCB or an FCC attorney.]**

### 1.4 Cost of a Part 15B test

**Unverified.** I found no official source stating a price. Get quotes from two or three labs. Ask each to bundle:
- Part 15B (FCC Class B, using ANSI C63.4);
- the KDB 996369 host spot check;
- optionally ICES-003 for Canada.

### 1.5 Future I2S microphone

A microphone adds no FCC intentional-radiator issue, but it changes the hardware. Re-evaluate or re-test Part 15B after the change (2.906(b) covers only "identical" units, per 2.908). Privacy and children's privacy rules (COPPA) become relevant, especially if the product is marketed to children. **[CONFIRM with an attorney.]**

---

## 2. Power: no adapter vs bundled adapter, and USB-C

### Option A: no adapter (the user brings a phone charger)

- No DOE external power supply (EPS) obligations fall on you. 10 CFR 430.32(w)(3), verified: the EPS standards "shall not constitute an energy conservation standard for the separate end-use product to which the external power supply is connected."
- Specify in the manual and on the listing: "USB-C, 5 V ⎓ 3 A (15 W) recommended; use a UL/ETL-listed adapter."
- FCC Part 15B testing should still use a representative adapter.

### Option B: you bundle an adapter (you become its importer)

- **DOE efficiency, 10 CFR 430.32(w), verified (eCFR current to 2026-11-25).**
  - Direct-operation EPS made on or after Feb 10, 2016 must meet **Level VI**.
  - (w)(4): it "shall be clearly and permanently marked in accordance with the International Efficiency Marking Protocol." In practice this is the Roman numeral "VI" on the label.
  - The basic model must be certified to DOE through the CCMS database (10 CFR 429). I did not open part 429 in this session; the CCMS duty is a secondary claim (CTA filing). **[CONFIRM that the adapter maker has a CCMS listing, or that you as importer certify.]**
  - USB-PD "adaptive" supplies are tested at their lowest and highest output voltages under DOE's test procedure. **Unverified**: I did not open Appendix Z.
- **California (CEC Title 20, MAEDbS).**
  - CEC guidance says federally regulated products such as battery chargers must be listed in CEC's MAEDbS database to be sold in California. The source is a 2018 CEC advisory on battery chargers; EPS appears among federally regulated appliances in CEC dockets.
  - I did not confirm current EPS-specific MAEDbS text. **Unverified.** **[CONFIRM the adapter has a MAEDbS listing.]**
- **Safety listing (UL/ETL).**
  - No federal statute or CPSC rule found requires UL/ETL listing for a consumer USB adapter. **Unverified as a negative**; it is based on not finding one.
  - Retail and Amazon in practice, plus product liability, mean you should only bundle an adapter that is **NRTL-listed (UL, ETL/Intertek, CSA, TÜV) to UL/IEC 62368-1**.
  - Amazon has been reported to request UL test reports for electronics (seller-forum reports only, not an official page).
  - The bundled EPS is itself a Part 15 device (external switching power supply, Class B, SDoC or certification under 15.101(a), verified). Get the supplier's FCC SDoC and test report.
- **Tariff note.** An adapter in the same retail box is normally classified with the set (GRI 3(b)). Shipped separately, it would be 8504.40.95 (general rate Free, Section 301 List 3 at 25%, verified in HTS Ch. 99). It is also subject to the 12.5% forced-labor Section 301 duty: it appears in note 52 only under the civil-aircraft exemption, which does not apply to you.

### USB-C sink design (brief engineering notes, not regulatory)

- For 5 V only, a USB-C sink needs 5.1 kΩ Rd pull-downs on CC1/CC2. No PD controller is needed.
- 3 A at 5 V is only available if the source advertises "3.0 A" via Rp. Read the CC voltage, or cap brightness in firmware, so you never draw more than the advertised current (500/900 mA, 1.5 A or 3 A).
- WS2812B strips can draw about 50–60 mA per LED at full white, so a firmware current limit and a fuse or PTC are prudent.
- USB-IF certification and logo use are optional and need a USB-IF license. **Unverified**: no USB-IF page opened.

---

## 3. Other US rules

### 3.1 CPSC: certificates and children's products

- **16 CFR 1110.5, verified.** "Finished products subject to a consumer product safety rule under the CPSA, or similar rule, ban, standard, or regulation under any other law enforced by the Commission, which are imported … must be accompanied by a finished product certificate."
  - For a general-use (adult) USB-powered LED controller and strip, I found no specific CPSC rule.
  - So **a GCC is likely not legally required**. Many importers issue one anyway, and Amazon may ask for one.
  - **[CONFIRM with an attorney or CPSC compliance consultant that no CPSC rule applies, e.g., none applies to the strip, plug or cord set.]**
- **CPSC eFiling, verified (CPSC release 26-604, Jul 8, 2026).** "eFiling program is now in effect, requiring importers of regulated consumer products" to file certificate data electronically with CBP at entry. Foreign-trade-zone (FTZ) entries follow from Jan 8, 2027. "It creates no new testing, certification, or compliance obligations."
  - If no CPSC rule applies, there is likely nothing to eFile. Your customs broker will need to confirm this, and may need to file a "no certificate required" disclaim. **Unverified.** **[CONFIRM with your customs broker.]**
- **Children's product decision. [DECISION]**
  - CPSC definition (cpsc.gov children's products page, verified): "a consumer product designed or intended primarily for children 12 years of age or younger." CPSC weighs the stated intended use, the marketing, consumer perception and the Age Determination Guidelines.
  - Verified on that page: children's products "are required to undergo third-party testing and to have a written Children's Product Certificate (CPC)."
  - If the product is marketed for kids' rooms or as a toy, you also face the following. These items are from my knowledge; I could not open the CPSC pages (403), so they are **unverified here**:
    - testing at a **CPSC-accepted** lab;
    - a total lead content limit of 100 ppm in accessible parts;
    - a lead-in-paint limit of 90 ppm;
    - permanent **tracking labels** (CPSIA §14(a)(5));
    - possibly ASTM F963 (toys) and small-parts rules;
    - **COPPA** for any app or account, plus extra microphone and privacy issues.
  - **Recommendation:** market it as a general-audience or adult decor product. Avoid kid imagery and "for kids" claims unless you are ready to meet children's product obligations. **[CONFIRM with an attorney.]**

### 3.2 California Proposition 65

- **Unverified.** p65warnings.ca.gov returned an empty page to the fetch tool.
- From general knowledge, to confirm:
  - businesses with fewer than 10 employees are exempt;
  - internet sales need a warning on the product page or before purchase if a listed chemical exposure is possible;
  - PVC cable jackets and solder can contain lead or phthalates (e.g., DEHP);
  - OEHHA amended the safe-harbor short-form warning rules, with changes effective Jan 1, 2025 and a transition period.
- Amazon commonly asks sellers to state whether a Prop 65 warning applies (secondary; Amazon policy page not opened).
- **[CONFIRM with an attorney; ask the factory for a lead/phthalate test (e.g., RoHS-type) of the cable and strip.]**

### 3.3 Country-of-origin marking

- **19 CFR 134.11, verified.** "every article of foreign origin (or its container) imported into the United States shall be marked in a conspicuous place as legibly, indelibly, and permanently as the nature of the article (or container) will permit … to indicate to an ultimate purchaser in the United States the English name of the country of origin."
- **19 CFR 134.41, verified.** Marking must be "legible, indelible, and permanent."
- Use "Made in China" on the device (molded or printed) **and** on the retail box.
- If the module and firmware were US-designed but assembled in China, the origin is still China for marking and tariffs, unless a substantial transformation happens elsewhere. **[CONFIRM with a customs broker.]**

### 3.4 E-waste

- WEEE is EU-only.
- Some US states run e-waste programs, but most cover TVs, monitors and computers, not small LED controllers. **Unverified; optional.**
- Note battery laws do not apply because there is no battery.

### 3.5 UL/ETL in general

- There is no federal requirement that I found for UL/ETL listing of a 5 V USB-powered consumer device. **Unverified as a negative.**
- Amazon and big-box retailers may ask for safety test reports. Expect UL 62368-1, or UL 8750 / UL 2108 / UL 1598 for LED lighting; this is my inference, unverified.
- Budget for at least a 62368-1 or "UL 8750-style" test report from an ISO 17025 lab.

---

## 4. Amazon US

Most Seller Central help pages need a login. The fetch of `sellercentral.amazon.com/help/hub/reference/external/G3B6R6AW2HCNJFE3` returned only the public Seller Central shell. I could read the **Radio Frequency Devices** help node through Amazon's public help mirror at `digprjsurvey.amazon.com/csad/help/node/G3B6R6AW2HCNJFE3`; the mirror is unusual, so treat it with care. Other nodes on that mirror returned no content.

- **RF devices policy (Amazon help node G3B6R6AW2HCNJFE3, opened via the public mirror).**
  - "RF devices offered for sale on Amazon must be authorized using the appropriate FCC equipment authorization procedure."
  - Prohibited: devices requiring certification that are not certified; SDoC-type devices not authorized; and devices claiming SDoC that "do not have a responsible party for compliance in the United States."
  - In the listing you fill in the "FCC Radio Frequency Emission Compliance" attribute. Per seller forums and TÜV SÜD, this has been mandatory since about 2022.
  - For your product, enter the module FCC ID (2AC7Z-…) and/or your SDoC details with the **US responsible party**.
  - Sellers report automated mis-flags and SDoC rejections (forum posts, secondary).
- **Safety and compliance documents.**
  - Amazon's requirements "vary depending on your product type, category, and the marketplace" (Amazon staff reply in the seller forum; secondary).
  - Expect requests via Account Health, "Manage your compliance", for: the FCC SDoC/test report, a safety test report from an ISO 17025 lab (UL/IEC 62368-1, or an LED-lighting standard), a GCC if applicable, the Prop 65 status, and product images showing the labels.
  - **Unverified**: no official Amazon electronics compliance page opened.
- **GTIN/UPC.**
  - Secondary (seller forums): you can request a GTIN exemption per brand and product type, with 2–9 photos showing the brand on product and packaging.
  - UPCs should be bought from **GS1 US**, because Amazon checks the GS1 database. **Unverified**: the official Amazon GTIN page was not opened.
  - With Brand Registry, the exemption is usually simpler.
- **Brand Registry (sell.amazon.com/brand-registry, verified).**
  - You need "an active, registered trademark or a pending trademark application" from a government trademark office of a country with an Amazon store.
  - The brand must appear on a logo permanently affixed to the product or packaging.
  - Word marks and design marks are accepted. The program is free.
  - **[CONFIRM USPTO filing strategy with a trademark attorney.]**
- **FBA.** No battery means no lithium or dangerous-goods review is expected. Standard FBA labeling and prep (FNSKU, poly-bag/suffocation warning if bagged) applies. **Unverified**: FBA prep pages not opened.

---

## 5. Tariffs (as of 2026-11-28)

### 5.1 Legal status timeline

| Measure | Status on 2026-11-28 | Source / level |
|---|---|---|
| IEEPA "fentanyl" tariff on China (9903.01.20/.24) | 10% from Feb 4, 2025, 20% from Mar 4, 2025, 10% from Nov 10, 2025 (the Nov 10 date is in the HTS note text). **Ended:** the Supreme Court held on Feb 20, 2026 that IEEPA does not authorize tariffs, and CBP stopped collecting on entries from **Feb 24, 2026** (CSMS #67834313) | HTS Ch. 99 Rev. 23 note 2(s)/(u) (verified text). Ruling and CSMS: secondary (Thomson Reuters, EY, Global Trade Alert) |
| IEEPA "reciprocal" tariff (10% on China under the Nov 2025 truce) | **Ended** Feb 24, 2026 (same basis). Refunds via the CBP "CAPE" process | Secondary (EY, Thomson Reuters, BDO). The White House fact sheet of Nov 1, 2025 (secondary summary) set the truce terms |
| Section 122 10% global surcharge | Effective Feb 24, 2026. **Expired at close of Jul 23, 2026** | HTS Ch. 99 note 2(aa) compiler's note: "headings 9903.03.01–9903.03.11 expired at the close of July 23, 2026. See 91 Fed. Reg. 9339." (verified) |
| Section 301 China (2018–2019 Lists 1–4A, 9903.88.xx) | **In effect.** Lists 1, 2, 3: +25%. Four-year review continued Oct 2026 (secondary) | HTS Ch. 99 Rev. 23, US note 20 (verified) |
| **Section 301 "forced labor" action (9903.05.31 for China)** | **In effect from 12:01 a.m. ET Jul 24, 2026:** China +12.5%, stacking with other Ch. 99 duties (note 52(a)), except products listed in note 52(b)–(k) | USTR notice / 2026-15181 (91 FR, Jul 28, 2026), verified; HTS Ch. 99 heading 9903.05.31, verified |
| Section 301 "structural excess capacity" (14 economies, incl. China) | **Proposed only**, Nov 25, 2026. China: "up to 20 percent (net of the forced labor Section 301 rate)"; Annex A up to 10%; Annex B exempt (largely consumer goods); possible 40% escalation. Comments due Jan 5, 2027; hearing Jan 25, 2027 | Secondary (Holland & Knight, Wiley, KPMG). USTR release not opened |
| Section 232 semiconductors | 25% on certain advanced computing chips only (from Jan 15, 2026). Not expected to cover an ESP32 LED controller | Secondary (EY, White & Case) |
| Section 232 steel/aluminum derivatives | Candidate HTS codes were **not** found in the Ch. 99 derivative lists I searched | HTS Ch. 99 text search, verified, partial |
| De minimis ($800) | **Suspended for all countries** since Aug 29, 2025 (China since May 2, 2025). Continued by EO 14388 (Feb 20, 2026). A CBP interim rule (Jun 2026) makes the suspension indefinite. Statutory repeal Jul 1, 2027 (OBBBA). Oct 8, 2026 CBP **proposed** rule on low-value shipments | FR API: 2026-20650 is a Proposed Rule (verified). The rest is secondary |

### 5.2 Classification candidates and estimated duty

**HTSUS Revision 23 (2026), from hts.usitc.gov, opened 2026-11-28.** Section 301 list membership was verified in the Ch. 99 text (US note 20). Forced-labor exemptions were verified in note 52 and in USTR's Annex I.

| HTS code | Description | General (MFN) | Section 301 (2018 lists) | Section 301 forced labor (Jul 24, 2026) | IEEPA / Sec. 122 | **Total ad valorem (est.)** | When it applies |
|---|---|---|---|---|---|---|---|
| **9405.42.8440** | Luminaires and lighting fittings designed for use solely with LED sources, other (stat. -10 "lighting sets", -40 "other") | 3.9% | **25%** (List 3, 9903.88.03, note 20(f)) | **12.5%** (9903.05.31; not exempt) | 0% (ended) | **41.4%** | **Most likely** if sold as a kit (controller + LED strip), or the strip with integrated controller. Essential character is lighting (GRI 3(b)). Ch. 99 notes cite Section 301 exclusions for LED strip-type goods under 9405.40.8440 / 9405.42.8440, which suggests CBP practice classifies such goods here |
| 8543.70.98 (.60) | Other electrical machines/apparatus with individual functions n.e.s. (note: **8543.70.99 no longer exists**; the current "Other" is 8543.70.98) | 2.6% | **25%** (List 2, 9903.88.02, note 20(d)) | 12.5% | 0% | **40.1%** | Controller sold alone, if not a controller of 8537 |
| 8537.10.91 (.70) | Boards, panels, consoles … for electric control, ≤1,000 V, other | 2.7% | **25%** (List 3) | 12.5% | 0% | **40.2%** | Alternative for a controller sold alone |
| 8541.41.00 | Light-emitting diodes (LED) | Free | **25%** (List 1, 9903.88.01) | **0%** (exempt under note 52(b) / 9903.05.86) | 0% | **25%** | Loose LED components only; not your finished product |
| 8539.52.00 | LED lamps (bulbs) | 2% | not checked | not checked | — | — | Unlikely (bulb-type lamps only) |
| 8504.40.95 | Static converters (USB adapter, if shipped separately) | Free | **25%** (List 3) | 12.5% (only civil-aircraft exemption applies) | 0% | **37.5%** | Bundled adapter imported separately |
| 8517.62.00 | Data reception/transmission machines (Wi-Fi) | Free | not verified | 0% (exempt, note 52(b)) | — | unverified | Unlikely. The function is lighting control, not data networking. **[Broker]** |

**Fees on top, verified in eCFR 19 CFR 24.23 / 24.24.**
- MPF ad valorem 0.3464% on formal entries.
- FY2026 minimum $33.58 and maximum $651.50 (CBP Dec. 25-10, 90 FR, Jul 23, 2025, via govinfo; secondary summary).
- FY2027 (from Oct 1, 2026) minimum **$34.58** and maximum **$670.86** (FR public-inspection 2026-15530; secondary, not opened).
- HMF 0.125% of value, ocean shipments only (19 CFR 24.24(a), verified).
- Informal entries (≤ $2,500) pay a flat MPF instead. De minimis is unavailable.

**Worked example (ESTIMATE, confirm with a licensed customs broker).** HTS 9405.42.8440, customs value $10,000 per ocean shipment.

| Item | Amount |
|---|---|
| General duty 3.9% | $390 |
| Section 301 List 3, 25% | $2,500 |
| Section 301 forced labor, 12.5% | $1,250 |
| **Duties** | **$4,140 (41.4%)** |
| MPF 0.3464% | $34.64 (just above the FY2027 $34.58 minimum) |
| HMF 0.125% | $12.50 |
| **Total about** | **$4,187 ≈ 41.9% of customs value** |

Possible upside risk:
- If the Nov 25, 2026 proposed excess-capacity action is finalized at "up to 20% net of forced labor", the forced-labor plus excess-capacity layer could total about 20%, i.e. about +7.5 points, giving **≈ 49%**.
- The 40% alternative would raise it more.
- Annex B (consumer goods) could exempt it.
- Watch for an effective date in early 2027. A US–China "Kuala Lumpur" truce is reported to expire Jan 10, 2027 (secondary).

**Recommendations.**
1. Get a **binding ruling** from CBP via eRulings (CBP's online ruling request system) **before** volume production. Search CROSS (rulings.cbp.gov) for LED strip and controller kit rulings first. **[Customs broker or customs attorney]**
2. Ask the broker about:
   - first-sale valuation;
   - Section 301 exclusions, which are limited (9903.88.69), so check whether any covers LED strip lights;
   - whether moving final assembly outside China would legally change origin. This needs substantial transformation; transshipment is illegal.
3. Re-check the HTS Ch. 99 and USTR pages just before each shipment. Rates changed at least five times between Feb 2025 and Nov 2026.

---

## 6. Confirm-with-a-professional checklist

**FCC test lab / TCB**
- [ ] The host fits the module grant conditions: mobile, more than 20 cm, approved antenna, no portable use. Confirm whether a Class II permissive change is needed.
- [ ] Scope under the current KDB 996369 D04: Part 15B Class B (ANSI C63.4) plus a radiated spurious-emissions spot check with the module transmitting. Strip length and adapter used in the test setup.
- [ ] Lab ownership: not a "prohibited entity" (2.906(a)(1)). ISO 17025 accreditation. Whether to use a US or reciprocal-economy lab given the FCC 26-73 FNPRM.
- [ ] Label text and location ("Contains FCC ID: 2AC7Z-…" plus the 15.19 statement). E-label not applicable without a display.
- [ ] Re-test plan when the I2S microphone is added.
- [ ] Quote for 15B testing (cost unverified).

**Attorney (FCC / product liability / IP)**
- [ ] US responsible party for SDoC (2.1077): your US entity.
- [ ] Children's product decision and marketing claims (CPSIA, CPC, tracking labels, COPPA).
- [ ] Prop 65 warning need and the small-business exemption.
- [ ] Trademark filing for Brand Registry (USPTO).
- [ ] Privacy policy if a microphone is added.

**Customs broker / customs attorney**
- [ ] HTS classification (9405.42.8440 vs 8543.70.98 vs 8537.10.91). File for a CBP binding ruling (eRulings).
- [ ] Current Chapter 99 stack at the date of entry: Section 301 List 3, forced-labor 9903.05.31, any finalized excess-capacity action.
- [ ] CPSC eFiling handling (certificate or disclaim) for each entry.
- [ ] MPF/HMF, importer of record, bond, and country-of-origin marking.
- [ ] Any IEEPA refund eligibility, if you imported between Feb 2025 and Feb 23, 2026.

**Safety lab / adapter supplier (if bundling an adapter)**
- [ ] UL/IEC 62368-1 NRTL listing, DOE Level VI marking and CCMS listing, CEC MAEDbS listing, FCC SDoC for the adapter.
- [ ] A safety test report for the controller and strip that Amazon will accept (ISO 17025).

---

## 7. URLs checked (2026-11-28)

**Opened** means I read the content. **Not opened** means blocked or returned nothing; any claim from it is listed as secondary or unverified.

| URL | Opened? | Used for |
|---|---|---|
| https://www.ecfr.gov/api/versioner/v1/full/2026-11-25/title-47.xml (sections 15.19, 15.21, 15.101, 15.105, 15.212, 2.906, 2.938, 2.1077) | Yes | FCC rules text |
| https://www.ecfr.gov/api/versioner/v1/full/2026-11-25/title-10.xml (430.32) | Yes | DOE EPS Level VI |
| https://www.ecfr.gov/api/versioner/v1/full/2026-11-25/title-16.xml (1110.5) | Yes | CPSC certificate trigger |
| https://www.ecfr.gov/api/versioner/v1/full/2026-11-25/title-19.xml (134.11, 134.41, 24.23, 24.24) | Yes | Origin marking, MPF, HMF |
| https://www.espressif.com/sites/default/files/Espressif%20Systems%202AC7Z-ESP32WROOM32E%20FCC%20Grant-DTS.pdf | Yes | WROOM-32E grant |
| https://www.espressif.com/sites/default/files/ESP32-S3-WROOM-1%20FCC%20Certification.pdf | Yes | S3-WROOM-1 grant |
| https://www.espressif.com/en/support/documents/certificates | Yes | Certificate listing (page says it "will be closed soon") |
| https://apps.fcc.gov/oetcf/kdb/… (KDB 996369, 784748) | **No** (Access Denied) | — |
| https://apps.fcc.gov/oetcf/eas/ (FCC ID search) | Not attempted (apps.fcc.gov blocked) | Grants verified via Espressif-hosted PDFs instead |
| https://docs.fcc.gov/public/attachments/FCC-26-73A1.txt | Yes | Oct 29, 2026 test-lab order |
| https://docs.fcc.gov/public/attachments/DOC-426300A1.txt | Yes | FCC press release, Oct 29, 2026 |
| https://docs.fcc.gov/public/attachments/DOC-422289A1.txt | Yes | FCC release, Jun 9, 2026 ("Bad Labs") |
| https://docs.fcc.gov/public/attachments/FCC-26-28A1.txt | Downloaded, not reviewed in detail | Apr 2026 Second R&O |
| https://www.fcc.gov/supplychain/coveredlist | **No** (403) | — |
| https://www.fcc.gov/sites/default/files/33-Modules-Integration-Instructions-TCB_Oct_2023.pdf | **No** (403/HTML) | — |
| https://hts.usitc.gov/reststop/search?keyword=… (9405.42, 8543.70, 8541.41, 8539.52, 8537.10, 8504.40, 8517.62) | Yes | General rates |
| https://hts.usitc.gov/reststop/file?release=currentRelease&filename=Chapter%2099 | Yes (Rev. 23, 2026) | Section 301 lists, 9903.05.31, notes 2(aa), 52 |
| https://ustr.gov/sites/default/files/files/Press/Releases/2026/FLIP%20301%20Investigation%20Final%20Action%20FRN%207-23-26%20FINAL.pdf | Yes | Forced-labor Section 301 action and annexes |
| https://www.federalregister.gov/api/v1/documents/2026-15181.json | Yes | FR metadata for the forced-labor notice |
| https://www.federalregister.gov/api/v1/documents/2026-20650.json | Yes | Low-value shipments (proposed rule) |
| https://www.federalregister.gov/documents/2026/07/28/2026-15181/… | **No** (redirect to unblock page) | — |
| https://ustr.gov/about/policy-offices/press-office/press-releases/2026/november/ustr-makes-determinations-and-proposes-actions-14-section-301-investigations-relating-structural | Not opened | Cited via Holland & Knight |
| https://www.hklaw.com/en/insights/publications/2026/11/ustr-proposes-tariffs-following-14-section-301 | Yes (secondary) | Excess-capacity proposal |
| https://cpsc.gov/Newsroom/News-Releases/2026/CPSC-Implements-Mandatory-eFiling-for-Certificates-of-Compliance-Targeting-Dangerous-Foreign-Imports | Yes | eFiling |
| https://www.cpsc.gov/Business--Manufacturing/Business-Education/childrens-products | Yes | Children's product definition, CPC |
| https://www.cpsc.gov/Business--Manufacturing/Testing-Certification/General-Certificate-of-Conformity-GCC | **No** (403) | — |
| https://www.cpsc.gov/…/Total-Lead-Content and …/Tracking-Labels | **No** (403) | — |
| https://www.p65warnings.ca.gov/new-proposition-65-warnings | **No** (empty) | — |
| https://www.energy.ca.gov/sites/default/files/2020-05/2018-06-07_Battery_Chargers_Advisory_ada.pdf | Search snippet only | MAEDbS (secondary) |
| https://digprjsurvey.amazon.com/csad/help/node/G3B6R6AW2HCNJFE3 | Yes (Amazon public help mirror) | RF devices policy |
| https://sellercentral.amazon.com/help/hub/reference/external/G3B6R6AW2HCNJFE3 | **No** (login shell only) | — |
| Amazon help nodes G200426310 (GTIN), G200164490, others | **No** (no content without login) | — |
| https://sell.amazon.com/brand-registry | Yes | Brand Registry eligibility |
| Secondary: Steptoe, Inside Global Tech, Cooley (FCC labs); EY, Thomson Reuters, BDO, Global Trade Alert (IEEPA/SCOTUS/refunds); White House fact sheet Nov 1, 2025 (summarized via search); FedEx, Livingston (FY2027 MPF); Element, Nemko, Bureau Veritas (KDB 996369); TÜV SÜD, seller forums (Amazon RF and compliance) | Search summaries | Context only |

---

## 8. What could not be verified

- The current text and version of **KDB 996369 D04** and **KDB 784748**: apps.fcc.gov was blocked. The guidance on scope (spurious-emissions spot check; e-label only with a display) is secondary.
- The **FCC Covered List** page itself: that Espressif and your contract manufacturer are not listed.
- The FCC ID database (apps.fcc.gov EAS) directly. Grants were verified via Espressif-hosted grant PDFs.
- **Part 15B test cost:** no official source.
- The official texts of the **SCOTUS IEEPA decision** (Feb 20, 2026) and CBP **CSMS #67834313**. The end of IEEPA collection on Feb 24, 2026 comes from secondary sources, though it is consistent with the HTS (Section 122 headings effective Feb 24, 2026).
- The final rate and effective date of the **Section 301 excess-capacity** action on China (proposal only), and whether 9405.42 would fall in Annex A or B.
- **FY2027 MPF** minimum and maximum ($34.58 / $670.86): secondary.
- De minimis interim final rule (Jun 2026) and EO 14388: secondary.
- **Amazon** official pages on GTIN exemption, electronics compliance documents and FBA prep: login required.
- CPSC lead, tracking-label and GCC pages (403). **Prop 65** details (page empty). DOE CCMS (10 CFR 429) and DOE Appendix Z, not opened. CEC MAEDbS specifics for EPS. State e-waste law coverage.
- That no federal law requires UL/ETL listing for 5 V USB consumer devices. This is a finding that nothing was found, not a confirmed rule.
- Section 301 list status for 8539.52.00 and 8517.62.00 (not checked).
