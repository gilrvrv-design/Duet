# Assembly / fulfilment partners and custom packaging: research notes
Product: ESP32 controller + 1.25 m WS2812B strip in a slim rail + USB-C cable. First batch 50-100 units, then 500+. US market.
Date checked: 2026-11-28. Nobody was contacted, no accounts were created, no forms were submitted. Prices come only from public pages and public calculators, used without logging in.

---

## PART A: Assembly, firmware flashing, kitting and fulfilment partners

| # | Company | Country | PCBA | FW flashing | Box build / kitting | Custom packaging | Fulfilment | FCC / test support | Stated minimum | Lead time | Public pricing | Contact | Sources |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Seeed Studio Fusion** (One-Stop, Light Customization, Kitting) | China (Shenzhen); regional warehouses | Yes. PCBA orders start at 1 pc | Yes. Programming and test files are required for PCBA orders; custom firmware is "assessed case by case" | Kitting service page asks for "Number of kits" + BOM. DigiKey listing says kits "from as little as 5 kits". No explicit "box build" page found | Yes. Boxes, labels, sleeves, manuals, outer cartons (Light Customization) | Yes. Warehousing + order fulfilment, including crowdfunding bulk fulfilment | Functional testing, custom test fixtures. Certification: not stated | PCBA: 1 pc. Kitting: 5 kits (DigiKey listing, secondary). FW on Seeed's own products: "no MOQ" (blog, secondary) | Not stated | No figures. NRE + per-unit processing fees; see Pricing & Payment Policy PDF | fusion@seeed.io | wiki.seeedstudio.com/service_for_fusion_one_stop/ ; wiki.seeedstudio.com/service_for_fusion_light_customization/ ; wiki.seeedstudio.com/Service_for_Fusion_PCB ; seeedstudio.com/kitting-service.html (search snippet only) ; digikey.cn/zh/design-services-providers/seeed-studio (search snippet only) |
| 2 | **JLCPCB** | China | Yes (Standard PCBA) | Yes. Only after soldering; the board needs a programming interface; HEX/BIN; first board shown on video for sign-off | No box build found in help pages | Static-bag packaging only: $0.16/pc up to 20x20 cm | No | Basic function verification only | Not stated | Not stated | **Programming: $7.86 engineering fee + $7.86/hour labour** | jlcpcb.com help centre | jlcpcb.com/help/article/jlcpcb-supported-personalized-services ; jlcpcb.com/help/article/pcba-programming-service |
| 3 | **PCBWay** | China (Hangzhou/Shenzhen) | Yes. Quote form starts at 5 pcs | Yes. IC programming before soldering (DIP/SOP/QFP/QFN/BGA…); NDA available | Yes. Box build, mechanical assembly, kitting, labeling/bar coding, "documentation inclusion" | "Packaging for shipment" + "Package Box" custom service (no details) | Not stated | Functional test, burn-in, ESS. Company certs: UL, ISO 9001. No product certification service stated | PCBA 5 pcs. Box build: "no limits on quantity" (no figure) | PCBA 3-5 days. Box build: not stated | Prototype PCBA "from $29 for 20 pcs". Programming and box build: unverified, quote required | service@pcbway.com, +86 571 8503 9969, EMS inquiry form | pcbway.com/oem/electronics-manufacturing.html ; pcbway.com/pcb-assembly.html |
| 4 | **Elecrow** | China (Shenzhen) | Yes | Yes ("Software Programming & Flashing") | Yes. Box build, enclosure, cable/harness, system integration; homepage lists "sub-assembly and kitting" (search snippet) | Yes. "Custom packaging with labeling" | Not stated | Testing listed. Certs claimed: ISO9001/13485/14001, IATF16949 (search snippet) | Not stated ("prototype to mass production") | Not stated | Unverified, quote required | elecrow.com/contacts ; service@elecrow.com | elecrow.com/box-build-and-final-assembly-service.html |
| 5 | **NextPCB** (HQ Online) | China (Shenzhen) | Yes. "No MOQ, from one piece" | Yes. IC programming + test jig support (2026 catalog) | Box build not on PCBA page. A Crowd Supply page (403, snippet only) says NextPCB offers "firmware programming, kitting and custom packaging" | Per the Crowd Supply snippet only; unverified | Unverified | Testing + jig support | No MOQ (PCBA) | ~7 business days (parts in stock) / ~20 (not), after DFA | Promo: "Free for 10 pcs, 50% off for 100 pcs turnkey assembly". Programming: unverified | support@nextpcb.com, nextpcb.com/contactus | nextpcb.com/pcb-assembly ; nextpcb.com/uploads/guide/NextPCB_Catalog 2026.pdf (snippet) ; crowdsupply.com/nextpcb/launchpad (403) |
| 6 | **MacroFab** | USA (Houston, TX) | Yes. "No contracts, no minimums"; quotes from 10 to 10K | Yes. In-circuit programming; pre-assembly flashing (search snippet of homepage) | Yes. Box-build page exists (403 to the fetcher); also warehousing/fulfilment and returns (search snippet) | Unverified | Yes per snippet ("warehousing and fulfillment") | Program + test from your test instructions | No minimums (startups page) | Not stated | Instant itemized quote online (needs upload; not done) | macrofab.com (instant quote) | macrofab.com/startups ; macrofab.com/box-build-assembly (403) |
| 7 | **CircuitHub** | USA (Boston area) | Yes | **Only for orders >200 units**; outside programming house; first-article fee ~$250 + shipping; adds up to 10 business days; not available on quick-turn | No box build found | No | No | First article | 200 units for programming | +10 business days for programming | FA fee ~$250 | circuithub.com | docs.circuithub.com/managing-projects/part-firmware-programming |
| 8 | **Bittele Electronics (7pcb)** | Canada (Markham, ON) + China/Malaysia | Yes. Low volume = 25-5,000 boards | Yes (IC programming; programming sample program for full turnkey) | Box build listed among services (careers page snippet) | Not stated | No | Functional test following your procedure | 25 boards ("low volume" definition) | 10/15/20-day quotes (snippet; conflicting) | No public prices; NRE/stencil waived on repeats | sales@7pcb.com, 1-888-812-1949 | 7pcb.com/low-volume-pcb-assembly ; 7pcb.com/Careers (snippet) |
| 9 | **Tempo Automation** | USA (SF) | **Defunct.** Chapter 7 liquidation filed 8 Dec 2023 (D. Del. 23-11969/23-11970) | – | – | – | – | – | – | – | – | – | inforuptcy.com (case 1:23-bk-11970) ; marketscreener.com joint-administration notice |
| 10 | **DCL Logistics** | USA | No | **Yes, re-flashing firmware** as a value-added service | Yes. Kitting/bundling, assembly, testing | Packaging sourcing (not custom design) | Yes. 3PL, DTC/B2B, returns | Testing | Not stated | Not stated | Quote only | dclcorp.com Get Started | dclcorp.com/services/fulfillment-solutions-for-hardware-brands/ |
| 11 | **Fulfillrite** | USA (NJ, UT) | No | Not on page (a search snippet mentions "firmware sorting"; unverified) | Yes. Kitting and assembly | Yes. Branded boxes, inserts, labels | Yes. 3PL | QC | **$399/month minimum (~140 orders)** | Not stated | Quote only | (855) 961-7766, fulfillrite.com/get-started/ | fulfillrite.com/consumer-electronics/ |
| 12 | **Crowd Supply / Mouser** | USA (ships from Mouser, Mansfield TX) | No | No | No (you ship finished goods in bulk) | No | Yes, but **only for projects launched on Crowd Supply** | Handles import, export compliance, VAT/sales tax | Must run a Crowd Supply campaign | – | Fees: unverified (guide page 403) | crowdsupply.com/apply | crowdsupply.com/guide/fulfillment-and-logistics (403; search snippet) ; crowdsupply.com/shipping (snippet) |
| 13 | **GLEDOPTO** (WLED ESP32 controller maker) | China (Shenzhen) | Own controllers | Unverified (sells WLED-flashed controllers) | – | Unverified | – | – | Not stated. A third-party listing says "1 pc for sample checking" | – | – | ray@gledopto.com, daemon@, chloe@, gracie@; WhatsApp 15820474300 | gledopto.com (homepage lists "OEM&ODM services") |
| 14 | **Athom (ATHOM Technology Co., Ltd.)** | China | Own controllers (pre-flashed WLED/Tasmota/ESPHome) | Pre-flashed open-source firmware; custom firmware/OEM program not found | – | – | – | – | Not stated | – | – | athom.tech/aboutus | athom.tech ; WLED forum warning thread (wled.discourse.group/t/psa-dont-buy-athom/10886) ; WLED docs note on the trademark dispute |
| 15 | **Alibaba generic WLED/ESP32 controller OEMs** (e.g. Shenzhen Caison, Sanxin Lighting, Kediya, "unbranded" Tuku) | China | Yes | Logo/package/label customization is listed; **firmware customization not confirmed** for any listing | – | Logo/label/package | – | – | Varies by listing | – | Varies | via Alibaba RFQ (not done) | alibaba.com/supplier/wled-controller.html (snippet) |

Part A notes:
- **No single source confirmed every service you need** (source the strip, rail and USB-C cable; flash; kit/assemble; branded box; US fulfilment). The closest: **Seeed Fusion** (PCBA + firmware + packaging + kitting + warehousing/fulfilment) and **PCBWay / Elecrow** (PCBA + programming + box build + packaging). For US-side alternatives: **MacroFab** (US CM, no minimums), or a US 3PL such as **DCL** that can re-flash and kit inbound goods.
- WLED is GPL-licensed. Shipping custom firmware on an off-the-shelf WLED controller has licensing implications; this was not checked further.
- An Alibaba seller blog warns that budget LED controllers have high failure rates. Treat any off-the-shelf ESP32 controller as a sample-first purchase.

---

## PART B: Custom packaging

Target sizes:
- **Long box:** rail ~135 x 6 x 5 cm. Priced as **53.25 x 2.5 x 2 in** interior.
- **Alternative A, 2-piece rail:** ~26 x 4 x 3 in. Holds two ~62.5 cm rail halves side by side, plus the controller and cable.
- **Alternative B, coiled strip / multi-piece rail:** ~35 x 20 x 6 cm. Priced as **14 x 8 x 2.5 in**. Note: a 35 cm box needs the rail in 4 or more pieces.

Packlane calculator settings: White b-flute, HDPrint matte, outside print, standard 7-12 business days. Prices were read from the public calculator on 2026-11-28 without logging in.

| Supplier | Long box (53.25 x 2.5 x 2 in) supported? | Max length found | Price @50 | Price @100 | Price @500 | MOQ | Contact | Source |
|---|---|---|---|---|---|---|---|---|
| **Packlane**, Standard Shipping Box (printed corrugated) | **No.** Calculator error: "53.25 is an unsupported Length. Enter a value between 3 and 31" | **31 in** | Alt A 26x4x3: **$4.88** ea; Alt B 14x8x2.5: **$5.12** ea | Alt A: **$3.88**; Alt B: **$4.11** | Alt A: **$2.74**; Alt B: **$2.93** | 1 unit | packlane.com (custom quote link on product page) | packlane.com/products/standard-shipping-box |
| **Packlane**, Mailer Box | **No.** Calculator error: "…Enter a value between 3 and 21" | **21 in** | Alt B 14x8x2.5: **$5.49** ea | **$4.49** | **$3.25** | 1 unit ("tiny minimum order, one") | as above | packlane.com/products/mailer-box |
| **EcoEnclose**, custom RSC shipping box | **Probably no.** In one configurator run, 54x4x4 in returned "We cannot cut the dimensions you've inputted for this shipping box". A rerun did not reproduce it. Minimum dimension input is 4 in. Unverified; ask them | Unverified | Unverified | Alt B (14x8x5, unbranded tier as displayed): **$2.47** (50+ tier) | Alt B: **$2.14** (500+ tier) | 1 unbranded; **100 branded**. Print plates **$95+ (1 panel), ~$200 mid, $300-800 full**, one-time per design | ecoenclose.com custom request | ecoenclose.com/shop/custom-shipping-boxes/ |
| **Arka** | Unverified. "Virtually any size… with some restrictions"; preset examples go up to 22x22x22 | Unverified | Unverified, quote required (page shows "Starting at $2.83/unit" for shippers) | Unverified | Unverified | Branded mailer/shipper: 1 sample, then 10+. Custom-size cartons: 250 | support@arka.com, custom quote page | arka.com/faq ; arka.com/products/custom-shipping-boxes |
| **Refine Packaging** | Unverified. No size limits published | Unverified | Below MOQ | Unverified, quote required | Unverified, quote required | **100** | 1-800-725-9660, refinepackaging.com/get-free-quote/ | refinepackaging.com/?p=1359 (FAQ) |
| **Salazar Packaging** (Oswego, IL) | Unverified (makes RSC, die-cut mailers, paperboard, rigid boxes) | Unverified | Unverified, quote required | Unverified, quote required | Unverified, quote required | Not published | 630-551-1700, salazarpackaging.com/contact-us/ | salazarpackaging.com |
| **Fantastapack** | Unverified. A third-party page says max depth 3 in, min 4x4x0.5 in | Unverified | Unverified (no calculator rendered for the fetcher) | Unverified | Unverified | "No minimum" (third-party snippet) | fantastapack.com | search snippet only |
| **The Custom Boxes** (thecustomboxes.com) | Unverified. Quote-form site | Unverified | Unverified, quote required | Unverified, quote required | Unverified, quote required | Unverified | thecustomboxes.com quote form | thecustomboxes.com (homepage only shows a contact form) |
| **Pakible** | Could not verify the company still operates (site returned 503; the only coverage found is from 2015) | – | – | – | – | – | – | trendhunter.com (2015) |
| **Uline stock box (fallback, unprinted)** S-4555 "Tall" box **4 x 4 x 60 in** (inside), C-flute, 200# test, opens on the end | **Yes.** Fits a 53 in rail with ~7 in of void fill | 60 in | **$3.53** (25 tier) | **$3.32** | **$2.67** | Bundle of 25 | uline.com, 1-800-295-5510 | uline.com/Product/Detail/S-4555/… |
| Uline long box S-21568 **60 x 6 x 6 in** | Yes (oversized cross-section) | – | $4.20 (25 tier) | $3.95 | $3.40 | Bundle of 15 | as above | uline.com/BL_406/Long-Boxes |
| Uline S-4675 48 x 4 x 4 in | **Too short** for 53 in | – | $2.61 | $2.37 | $1.94 | 25 | as above | uline.com/BL_406/Long-Boxes |
| Uline round kraft tube S-5575, 4 in dia x 60 in, end caps | Yes | 60 in | Unverified (price not read) | – | – | – | as above | uline.com/Product/Detail/S-5575/… (search snippet) |
| **Alibaba box factories**, e.g. The Forests Packaging Group "long size" corrugated (surfboard box, 200x60x15 cm listing) | Long formats are clearly made; a 135 cm slim box needs an RFQ | Listing size 200 cm | Below MOQ | Below MOQ | **$0.59/pc (500-999)**, $0.49 (1k+), $0.19 (5k+), **for the listed surfboard size, not ours**. Freight not included | **500** for custom logo/print | Alibaba RFQ (not done) | alibaba.com/product-introduction/Custom-Colorful-Plain-Kraft-Long-Size_60763379222.html |

Fallback for a branded long box: Uline 4x4x60 stock box plus a custom printed label or sticker. Label pricing was not checked (unverified). Arka lists stickers at a 100-unit minimum (arka.com/faq).

Shipping note: USPS Ground Advantage charges a nonstandard fee above 22 in length and a higher tier above 30 in (DMM 283; fee amounts are in Notice 123, not checked). A 53-60 in box always lands in the >30 in tier. A 26 in box (Alt A) lands in the 22-30 in tier. A 14 in box (Alt B) avoids length fees. Source: pe.usps.com/Text/DMM300/283.htm (search snippet).

---

## Key observations

**For 100 units:**
- **Assembly / flash / kit:** Seeed Fusion is the only partner whose public pages cover PCBA, firmware flashing, packaging customization, kitting and fulfilment together, with low minimums (PCBA 1 pc, kits from 5). PCBWay and Elecrow are close alternatives (programming + box build + packaging, but no published box-build minimum or pricing). JLCPCB only flashes boards it assembles ($7.86 + $7.86/hr). It has no box build, so it suits the controller PCBA only. CircuitHub is out below 200 units.
- If the controller is an off-the-shelf ESP32/WLED board, the founder could flash and kit 100 units themselves. Alternatively, a US 3PL that re-flashes and kits (DCL; Fulfillrite has a $399/month minimum) could do it once goods land.
- **Packaging:** low-minimum online printers do not support a 135 cm box (Packlane caps at 31 in for shipping boxes and 21 in for mailers). Practical options at 100 units:
  1. Unprinted **Uline 4x4x60 box (~$3.32 @100)** + branded sticker or sleeve.
  2. Redesign to a **2-piece rail** and use a **Packlane printed 26x4x3 box (~$3.88 @100)**.
  3. A **4-piece rail / coiled strip** in a 14x8x2.5 box (~$4.11 shipper or ~$4.49 mailer @100 at Packlane, or EcoEnclose ~$2.47 + a $95-800 plate). This also cuts shipping cost.

**For 500+ units:**
- Asking a Chinese partner (Seeed Fusion / PCBWay / Elecrow / NextPCB) for an all-in quote becomes attractive: PCBA + flashing + strip/rail/cable sourcing + kitting + branded box, shipped to a US 3PL or Seeed's warehouse.
- A full-length printed long box from an **Alibaba box factory** becomes possible (custom-print MOQ ~500; their surfboard-box listing shows $0.59/pc at 500, but our size and sea freight need an RFQ).
- Packlane 26x4x3 falls to ~$2.74 @500, and Uline 4x4x60 to ~$2.67 @500 (unprinted).
- A shorter box (2-piece rail) also avoids USPS's >30 in nonstandard-fee tier. That may matter more per unit than the box price itself.

---

## URL list (checked 2026-11-28)

| URL | Opened? |
|---|---|
| https://wiki.seeedstudio.com/service_for_fusion_one_stop/ | Yes |
| https://wiki.seeedstudio.com/service_for_fusion_light_customization/ | Yes |
| https://wiki.seeedstudio.com/Service_for_Fusion_PCB | Yes |
| https://www.seeedstudio.com/blog/seeed-home-page/agile-manufacture-service/ | No (403) |
| https://www.seeedstudio.com/kitting-service.html | Search snippet only |
| https://www.digikey.cn/zh/design-services-providers/seeed-studio | Search snippet only |
| https://files.seeedstudio.com/fusion/odm/PricingAndPaymentPolicyForCustomService.pdf | Not opened (linked from wiki) |
| https://jlcpcb.com/help/article/jlcpcb-supported-personalized-services | Yes |
| https://jlcpcb.com/help/article/pcba-programming-service | Search snippet only |
| https://www.pcbway.com/oem/electronics-manufacturing.html | Yes |
| https://www.pcbway.com/pcb-assembly.html | Yes |
| https://www.elecrow.com/box-build-and-final-assembly-service.html | Yes |
| https://www.nextpcb.com/pcb-assembly | Yes |
| https://www.nextpcb.com/uploads/guide/NextPCB_Catalog 2026.pdf | Search snippet only |
| https://www.crowdsupply.com/nextpcb/launchpad | No (403) |
| https://macrofab.com/startups | Yes |
| https://macrofab.com/box-build-assembly | No (403) |
| https://docs.circuithub.com/managing-projects/part-firmware-programming | Yes |
| https://7pcb.com/low-volume-pcb-assembly | Yes |
| https://www.7pcb.com/Careers | Search snippet only |
| https://www.inforuptcy.com/browse-filings/delaware-bankruptcy-court/1:23-bk-11970/bankruptcy-case-tempo-automation-inc | Search snippet only |
| https://dclcorp.com/services/fulfillment-solutions-for-hardware-brands/ | Yes |
| https://www.fulfillrite.com/consumer-electronics/ | Yes |
| https://www.crowdsupply.com/guide/fulfillment-and-logistics | No (403); search snippet |
| https://www.gledopto.com/ | Yes |
| https://www.athom.tech/ | Yes (partial) |
| https://wled.discourse.group/t/psa-dont-buy-athom/10886 | Search snippet only |
| https://www.alibaba.com/supplier/wled-controller.html | Search snippet only |
| https://packlane.com/products/standard-shipping-box | Yes (public calculator in headless browser) |
| https://packlane.com/products/mailer-box | Yes (public calculator in headless browser) |
| https://packlane.com/support/product-information | Yes (curl) |
| https://packlane.com/llms.txt | Yes (curl) |
| https://www.arka.com/faq | Yes |
| https://www.arka.com/products/custom-shipping-boxes | Yes (headless; no size calculator exposed) |
| https://ecoenclose.com/shop/custom-shipping-boxes/ | Yes (public configurator in headless browser; results partly unreliable, see notes) |
| https://refinepackaging.com/?p=1359 | Yes |
| https://www.salazarpackaging.com/ | Yes |
| https://www.fantastapack.com/ | Yes (no calculator rendered) |
| https://www.thecustomboxes.com/ | Yes (quote form only) |
| https://www.pakible.com/ | No (503) |
| https://www.uline.com/BL_406/Long-Boxes | Yes |
| https://www.uline.com/Product/Detail/S-4555/Corrugated-Boxes-200-Test/4-x-4-x-60-Tall-Corrugated-Boxes | Yes |
| https://www.uline.com/BL_3658/Triangle-Tubes | Yes (max 38 in, too short) |
| https://www.uline.com/Product/Detail/S-5575/Kraft-Mailing-Tubes/Kraft-Mailing-Tubes-with-End-Caps-4-x-60-125-thick | Search snippet only |
| https://www.alibaba.com/product-introduction/Custom-Colorful-Plain-Kraft-Long-Size_60763379222.html | Yes |
| https://pe.usps.com/Text/DMM300/283.htm | Search snippet only |

---

## Not verified / open questions
- Box-build, kitting and programming **prices, minimums and lead times** for Seeed Fusion, PCBWay, Elecrow, NextPCB, MacroFab and Bittele. All need a quote.
- Whether NextPCB really offers kitting and custom packaging (only a Crowd Supply snippet says so).
- Whether MacroFab offers warehousing/fulfilment today (search snippet only; the box-build page was 403).
- Whether GLEDOPTO, Athom or Alibaba WLED OEMs will flash **custom** (non-WLED) firmware and private-label. Not stated anywhere.
- FCC testing support: no partner page found that offers FCC certification as a service. An FCC lab would be a separate vendor (not researched).
- EcoEnclose maximum size: the configurator rejected 54x4x4 once but did not reproduce it. Its branded-box pricing (plates + unit) was not reliably captured.
- Max sizes and prices for Arka, Refine, Salazar, Fantastapack and The Custom Boxes. Pakible may no longer operate.
- Alibaba long-box pricing for 135 x 6 x 5 cm, plus freight and duties.
- Uline custom label pricing; the S-5575 tube price.
- USPS nonstandard fee dollar amounts (Notice 123).
- Crowd Supply fulfilment fees.
