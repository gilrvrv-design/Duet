# Rail + End Cap Housing: Process / Supplier / Cost Research

Date checked: 2026-11-28. No accounts were created, no files were uploaded, no forms were submitted and no one was contacted.

Product assumptions: a rail about 1,225-1,250 mm long holding a WS2812B 144/m strip (about 10-12 mm wide) under a black or smoked diffuser, plus one end cap (about 60x30x15 mm) holding an ESP32 board (about 50x25x10 mm) with a USB-C opening.

Labels used below:
- **published range**: a range the manufacturer itself publishes.
- **3rd-party**: a figure from a blog, marketplace or reseller.
- **estimate**: my own arithmetic from a published rate. It is not a quote.
- **unverified**: I could not find a public figure. Getting one would need an account, a CAD upload or a sales contact.

---

## 1. Key constraint: shipping size (this decides one-piece vs split rail)

| Rule | UPS | FedEx | Source |
|---|---|---|---|
| Additional Handling (dimension) | Longest side > 48 in **or** 2nd-longest > 30 in **or** length+girth > 105 in; from 26 Jan 2026 also a cubic trigger (> 10,368 in³, per a 3rd-party summary) | Longest side > 48 in **or** 2nd-longest > 30 in **or** length+girth > 105 in (girth = 2W + 2H) | UPS: https://www.ups.com/us/en/support/shipping-support/shipping-dimensions-weight/avoid-additional-shipping-fees and https://www.ups.com/assets/resources/media/en_US/additional_charges_daily.pdf ; FedEx: https://www.fedex.com/content/dam/fedex/us-united-states/services/Service_Guide_2026.pdf (2026 guide, effective 5 Jan 2026, updated 11 Sep 2026). Cubic trigger: https://www.easyship.com/blog/ups-surcharges (3rd-party) |
| Large Package / Oversize | Length+girth > 130 in **or** length > 96 in; 2026 guide adds > 17,280 in³ or > 110 lb. 90 lb minimum billable weight | Oversize: longest > 96 in **or** length+girth > 130 in; 90 lb minimum billable weight | UPS: https://www.ups.com/assets/resources/media/en_US/additional_charges_retail.pdf ; FedEx: Service_Guide_2026.pdf above and https://www.fedex.com/en-us/customer-support/faqs/business/surcharges-and-fees/what-is-an-oversize-charge.html |
| Maximum accepted size | 108 in length, 165 in length+girth, 150 lb | 165 in length+girth. Ground/Home Delivery: 108 in length. The guide's general limit says 119 in | Same documents as above |
| AH surcharge amount | 2026 Small Business guide: "Length-based" AH with a 40 lb minimum billable weight. The fee table (Weight $27.75 / All Other $17.50) is not clearly mapped to length. **Unverified** | Zone-dependent. **Unverified** | https://assets.ups.com/adobe/assets/urn:aaid:aem:bbf2553c-15e5-4b2d-abcd-b7445b13daa0/original/as/small-business-rate-guide-us-en.pdf |
| Large Package surcharge amount | 2026 Small Business guide: $105.50 commercial / $117.25 residential (from a search snippet of the official PDF) | **Unverified** | Same UPS PDF |

**What this means for this product**
- **One-piece rail box, about 130 x 8 x 6 cm (51.2 x 3.1 x 2.4 in):**
  - Longest side 51.2 in is over 48 in, so it **triggers Additional Handling at both UPS and FedEx**.
  - Length+girth is about 62 in, well under 105 and 130 in, so it is **not** a Large Package / Oversize shipment.
  - The UPS 40 lb minimum billable weight for length-based AH (2026 guide) makes a 1 kg parcel bill as 40 lb. That is a very large per-unit penalty for a consumer product.
- **Split rail:**
  - A **2-piece** rail (2 x ~625 mm) packs in a box of about 70 x 10 x 8 cm (27.6 in). That is under every threshold, so it ships as a normal parcel.
  - A **3-piece** rail (~410 mm segments) fits a box of about 45 cm.
- **Recommendation:** design for a 2-piece rail with an internal splice or connector. This is the main argument against a one-piece rail for direct-to-consumer shipping.
- **Caveat:** every official UPS and FedEx page and PDF returned "Access Denied" to WebFetch and curl from this environment. The figures above come from search-engine excerpts of those official URLs, cross-checked against 3rd-party summaries (easyship, redstagfulfillment, sifted). Re-check them in a browser before relying on them.

---

## 2. Process / supplier table by volume tier

### (a) Under 50 units (prototype / first batch)

| Process | Supplier | Tooling | Per-unit cost | MOQ | Lead time | Source URL | Notes |
|---|---|---|---|---|---|---|---|
| Off-the-shelf Al LED channel (rail) | Muzata U-channel (Amazon, Walmart, eBay) | None | About $5.3-9.5 per 1 m length in 6- and 10-packs, e.g. a 6-pack of 1 m black U101 with milky diffuser for $51.98 (about $8.66/m) (3rd-party retail) | 1 pack | Days | https://www.walmart.com/c/kp/led-channel-diffuser ; https://www.desertcart.us/products/38675704-muzata-10pack-3-3ft-1m-led-channel-aluminum-u-shape.md | Sold in 1 m lengths, so 1.25 m needs two pieces joined (or 2 m stock cut down). Standard diffusers are milky; a smoked/black diffuser is a separate SKU. Exact single-SKU price is unverified |
| Off-the-shelf Al LED channel | Klus (EU) via Mr Resistor UK | None | PDS ZMG black anodised 1000 mm: £7.92 ex VAT (sale price). **PDS4 per-metre price unverified** | 1 | Days | https://www.mr-resistor.co.uk/product/24651 (product list from search) | Klus sells 1 m / 2 m / 3 m stock lengths, and 2 m covers 1.25 m in one piece |
| Off-the-shelf Al LED channel | Superbright LEDs (Klus PDS-4-PLUS) | None | $13.99 each, 1 m black (page does not say which length the price applies to) | 1 | Days | https://www.superbrightleds.com/pds-4-plus-extrusion | Lens and end-cap prices were truncated (unverified) |
| Alibaba profile factory, cut to length + anodised | e.g. Toco and other Shenzhen/Foshan suppliers | None for catalogue profiles | $1.19/pc (1-9,999 pcs), $0.59/pc at 10k+ for a black anodised profile cut from 0.5 m; other listings $1.40-5.50/m (3rd-party listings) | Often 100-200 m or 100 pcs; samples often allowed | Listed as 4-7 days for up to 1,000 m | https://www.alibaba.com/product-introduction/toco-Aluminium-Led-Profile-Black-Led_1600089463826.html ; https://www.alibaba.com/product-introduction/U-V-Shape-Channel-Aluminum-LED_1600524934007.html | Freight to you is extra. A 1.25 m length triggers parcel AH (see section 1), so ask for sea or air freight to a 3PL |
| FDM 3D print (end cap, or rail in segments) | JLC3DP | None | **Unverified** (instant quote needs an upload). Site says "from $0.30" | 1 | 48-120 h (site-wide) | https://jlc3dp.com/capabilities/3d-printing-service ; https://jlc3dp.com/help/article/3d-printing-design-guideline | Max FDM size: ABS/ASA/PA12-CF 580x480x480 mm, PLA 250x250x300 mm. A 625 mm segment does **not** fit, so either 3 segments of ~410 mm or SLA |
| SLA 3D print (end cap; rail in 2 segments) | JLC3DP | None | **Unverified** | 1 | 48-120 h | https://jlc3dp.com/help/article/3d-printing-design-guideline | Max SLA size: 780x780x530 mm (Black Resin, JLC Black, 9600, 8001). A 625 mm segment fits diagonally or flat, which makes JLC SLA one of the few services that can print a half-rail. Black resin options exist |
| MJF PA12 (end cap) | JLC3DP | None | Published rate $0.275/g (cut from $0.35/g in Aug/Dec 2025; a July 2026 update exists but I could not read it). **Estimate:** a 10-15 g cap costs about $2.75-4.15 in material before surcharges and minimums | 1 | Help page says "from $1.00", 72 h build | https://jlc3dp.com/blog/drastic-material-price-cuts-and-adjusted-post-processing-service-fees ; https://3D.jlcpcb.com/help/article/200-PA12-HP-Nylon | Max MJF size: 370x276x360 mm, so no rail. Good for a grey/black end cap; it can be dyed black |
| FDM / SLS / PolyJet | PCBWay | None | **Unverified** (quote needs upload) | 1 | Unverified | https://www.pcbway.com/rapid-prototyping/3d-printing/3d-printing-FDM.html ; https://www.pcbway.com/rapid-prototyping/3d-printing/3d-printing-SLS.html | FDM max 600x500x500 mm, SLS max 400x390x390 mm, PolyJet max 490x390x200 mm. A 3rd-party table claims SLA up to 2100x700x800 mm (unverified on PCBWay's own pages) |
| Marketplace (FDM/SLA/MJF) | Craftcloud (All3DP) | None | All3DP test (15 Apr 2026): about $47 for an FDM PLA part and about $130 for an MJF PA12 part (3rd-party; part sizes differ from ours) | None ("no minimum order amounts") | Varies by vendor | https://craftcloud3d.com/en/p/3d-printing-services ; https://all3dp.com/1/uncover-real-3d-printing-service-costs/ | Max size depends on the vendor. All3DP lists up to 10 m FDM / 3.5 m SLA through large-format vendors, so a one-piece 1.25 m FDM rail is possible through some vendors. Unverified |
| Marketplace | Treatstock | None | Set by each vendor. **Unverified** | Varies | Varies | https://www.treatstock.com/c/the-tech-deck-llc?ln=en-US | Still operating as a marketplace in Nov 2026 |
| SLS/MJF/SLA | Shapeways | None | **Unverified** (quote form) | Unverified | Unverified | https://www.shapeways.com/ | **Operating**: site shows © 2008-2026, "Get a Quote", and a blog post dated 27 Oct 2026. Filed Chapter 7 in July 2024; assets were bought by founders and the Eindhoven team; the EU arm runs as Manuevo (https://3dprint.com/314952/shapeways-relaunched-with-all-assets-under-one-roof/). Max sizes not listed |
| SLS/MJF/SLA/FDM | Xometry | None | **Unverified** (instant quote needs an upload) | 1 | Unverified | https://support.xometry.com/hc/en-us/articles/216286528-What-s-the-maximum-size-of-a-part-you-can-print-} ; https://xometry.com/capabilities/3d-printing-service/large-scale | FDM 36x24x36 in (914 mm), so a 625 mm half-rail fits, and a 1.25 m one-piece fits only on the diagonal (not checked). MJF 15x11x15 in. SLA standard 29x25x21 in. SLS PA12 13x13x20 in |
| SLA/SLS/MJF | Protolabs | None | **Unverified** | 1 | Unverified | https://www.protolabs.com/en-gb/services/3d-printing/3d-printing-maximum-extents/ | SLA WaterShed / Xtreme White 736x635x533 mm, Accura Black 247x247x250 mm. SLS PA12 676x367x564 mm. MJF 284x380x380 mm |
| CNC aluminum end cap | JLCCNC | None | Homepage says "from $5.00" (not tied to a part). May 2026 price rise cites aluminum up about 20%. **Per-part price unverified** | 1 | About 3 days build | https://jlccnc.com/ ; https://jlccnc.com/news/price-adjustment-in-may-2026 | An anodised black Al cap matches an Al profile and looks premium. A USB-C cut-out and pocket mean 2+ setups |
| CNC | PCBWay / Xometry / Protolabs | None | **Unverified**. A 3rd-party review says PCBWay CNC starts at about $24.89 | 1 | Unverified | https://www.unionfab.com/blog/2026/03/jlc-vs-pcbway-vs-rapiddirect-vs-unionfab ; https://www.xometry.com/resources/machining/ways-save-money-cnc-prototypes/ | Xometry says setup cost dominates small quantities |

### (b) 50-500 units

| Process | Supplier | Tooling | Per-unit cost | MOQ | Lead time | Source URL | Notes |
|---|---|---|---|---|---|---|---|
| Catalogue Al profile, cut to 2 x ~620 mm, black anodised, with matching PC/PMMA smoked diffuser | Alibaba profile factories | None (catalogue die) | About $1.40-1.60/m at 100-999 m for a U/V channel; $0.59-1.19/pc for some cut-to-length SKUs (3rd-party listings). Black/smoked diffuser and end caps are separate lines | 100-500 m or 100 pcs typical; customised logo/packaging 100-5,000 pcs | Listed as 5-7 days production plus freight | https://www.alibaba.com/product-introduction/U-V-Shape-Channel-Aluminum-LED_1600524934007.html ; https://www.alibaba.com/product-introduction/toco-Aluminium-Led-Profile-Black-Led_1600089463826.html | **Best value in this tier.** Ask for a factory-cut length with a splice-pin hole. Verify the alloy (6063) and that the finish is anodised, not powder-coated |
| Catalogue Al profile (EU/US brand) | Klus / Superbright | None | About £8-$14 per 1 m retail (see tier a); distributor volume pricing unverified | 1 | Days | See tier a | Brand-name quality, roughly 5-10x the Alibaba price |
| End cap: MJF PA12 or SLA, batch | JLC3DP | None | **Estimate:** about $3-5 material per cap at $0.275/g. Real batch quote unverified | 1 | 2-5 days | https://jlc3dp.com/blog/drastic-material-price-cuts-and-adjusted-post-processing-service-fees | Workable up to a few hundred units. Surface needs dyeing or painting for a premium black finish |
| End cap: aluminum ("rapid") injection mould | Protolabs | Aluminum moulds "begin around $1,500" (published range) | **Unverified** (needs a quote) | Production as low as 25 pcs (published) | Moulds "in seven days or less"; parts "within a few days" (published) | https://www.protolabs.com/resources/blog/aluminum-mold-tooling-for-injection-molding/ ; https://www.protolabs.com/resources/design-tips/11-tips-to-reduce-injection-molding-costs/ | About 10,000 parts per aluminum mould "as a rule of thumb", often more. Max part 480x751 mm, 101 mm depth. Prototyping route is meant for < 2,000 lifetime parts |
| End cap: injection mould | PCBWay | **Unverified** | **Unverified** | "as little as a single prototype up to 10,000 production parts" | "molds ready in 15 days, parts shipped in 1 to 15 days" | https://pcbway.com/rapid-prototyping/injection-molding/ | Page says the starting cost is higher than CNC or 3D printing for small batches |
| End cap: injection mould | Xometry | "can cost up to $10,000" for a mid-level order of about 1,000-2,000 small parts (published range) | **Unverified** | Unverified | Unverified | https://www.xometry.com/resources/injection-molding/injection-molding-cost/ | Resin per lb (2020 Rex Plastics data): ABS $1.30, PC $2.30 |
| End cap: injection mould | Fictiv, ICOMold, Rex Plastics, JLC | **Unverified**: no public dollar figures on their own pages | **Unverified** | Unverified | Fictiv banner: steel "as fast as weeks" | https://www.fictiv.com/articles/steel-vs-aluminum-for-injection-molds | Rex Plastics' own page could not be reached. A 3rd-party page (abismould) attributes "$1,000-5,000 small single-cavity; about $12,000 average hand-sized" to Rex Plastics (unverified). ICOMold and JLC pricing pages were not found |
| End cap: CNC Al | JLCCNC / PCBWay | None | **Unverified** | 1 | Days | https://jlccnc.com/ | CNC caps above about 100 units are usually more expensive than an aluminum mould plus parts. Unverified for this part |

### (c) 1,000+ units

| Process | Supplier | Tooling | Per-unit cost | MOQ | Lead time | Source URL | Notes |
|---|---|---|---|---|---|---|---|
| Custom aluminum extrusion (own rail profile with integrated diffuser slot, splice channel and piano-friendly feet) | Gabrian | Dies "$400 to $1,000" for normal industrial profiles, "as high as $2,000" for large parts on 2,000-4,000 t presses (published range) | Al $1,500-3,500/metric ton; anodise or powder coat $1,200-1,400/t; simple drilling $200-300/t (published). **Estimate** for a profile of about 150-250 g/m at about $4,000-5,500/t all-in: about $0.60-1.40/m before cutting and packing | Not stated on the page | Tool 3-4 weeks; production within 1 week of sample approval | https://www.gabrian.com/cost-of-custom-aluminum-extrusions/ | The best per-unit option. The die cost is small relative to the volume |
| Custom aluminum extrusion | Aluminum Extruders Council (industry body) | 7-10 in circle-size presses: $1,000-2,000 solid, $1,200-4,000 hollow (published range, AEC white paper) | **Unverified** | "often 1,000 to 2,000 pounds per shape", or a minimum charge instead | Dies 2-3 weeks | https://aec.org/sites/default/files/2022-11/bcwhitepaper_rev01252019.pdf | 1,000 lb is about 450 kg, which is about 2,000-3,000 m of a light profile, or about 1,600-2,400 rails. That roughly matches a 1,000-2,000 unit run |
| Custom aluminum extrusion | Bonnell Aluminum, Taber Extrusions | **Unverified** (no public die charge) | **Unverified** | Taber (old, undated SlideShare deck): "No minimum order/production quantity". Bonnell: not published | Unverified | https://www.slideshare.net/slideshow/taber-extrusions-sales-presentation/161607723 ; https://www.steel-technology.com/products/bonnell-aluminum/custom-aluminum-extrusions | US domestic; expect higher per-kg prices than China |
| Custom aluminum extrusion | Alibaba extrusion factories | 3rd-party pages: $300 to $3,000+; a UK supplier says a few hundred to about £1,000 simple, £2,000+ complex | **Unverified** per m | 3rd-party: 500 kg per alloy/temper typical, 200 kg on existing dies; some claim no MOQ | 3rd-party: 2-3 weeks | https://get-it-made.co.uk/resources/how-much-does-aluminium-extrusion-cost | Many factories waive or refund the die cost above a volume threshold (unverified; ask) |
| Custom PC/PMMA diffuser extrusion (smoked or black-tinted, co-extruded) | Chinese lighting-profile extruders (HKTDC, Alibaba) | **Unverified**: no public die price found. Xometry says plastic extrusion tooling is "80-90% lower" than injection moulding (vendor claim) | Alibaba listing: $0.10-1.00/m at a 1,000 m MOQ for PC/PMMA diffuser profiles (3rd-party) | About 1,000 m, or 100 pcs on some listings | Unverified | https://www.xometry.com:443/capabilities/plastic-extrusion-services ; https://www.alibaba.com/product-introduction/OEM-Factory-Customized-Led-Extrusion-Profiles_1601153026887.html | A catalogue smoked diffuser that fits a catalogue profile avoids this tooling cost. PC costs about 30-40% more than PMMA (3rd-party) |
| End cap injection moulding, steel (P20/H13) | Protolabs / Xometry / Fictiv / China moulders | Protolabs: steel for million-part volumes "more than $50,000" (published, for high-volume multi-cavity). 3rd-party: single-cavity P20 $5,000-12,000; bridge P20 $3,000-5,000 | **Unverified**. Resin cost alone for a 10-15 g ABS/PC cap is about $0.03-0.08 (estimate from Xometry's resin $/lb) | Varies | Protolabs says steel tooling lead time is "months" | https://www.protolabs.com/resources/blog/aluminum-mold-tooling-for-injection-molding/ ; https://www.protolabs.com/resources/blog/aluminum-vs-steel-tooling/ ; https://www.mfgrobots.com/Article/mfg/it/54227.html (3rd-party) | Above 1,000 units, a single-cavity aluminum or P20 mould usually wins. Steel is only needed above about 10k-100k shots. The two end caps (controller end and blank end) could share one family mould |
| End cap injection moulding, aluminum | Protolabs | From about $1,500 (published range) | **Unverified** | 25 pcs | About 7 days | Same as above | About 10k+ shots, which covers 1,000-5,000 units comfortably |

---

## 3. Recommendation per tier

**(a) Under 50 units**
- **Rail:** buy a catalogue black-anodised aluminum U-channel with a smoked diffuser.
  - Either Klus or Muzata in 2 m lengths cut to 1,225-1,250 mm,
  - or two 1 m channels joined with a printed splice for the 2-piece design.
  - Cost is roughly $8-14/m (3rd-party retail), about $10-20 per rail.
- **End cap:** 3D print at JLC3DP. Use MJF PA12 dyed black, or SLA black resin for a smoother finish.
  - Material estimate about $3-5 per cap. The actual quote is unverified.
- **Rail feet / anti-scratch pads:** print in TPU.
- **Shipping:** hand-deliver, or accept the UPS/FedEx Additional Handling surcharge for one-piece rails.

**(b) 50-500 units**
- **Rail:** Alibaba catalogue profile, factory-cut into 2 x ~620 mm segments with a splice pin, black anodised, with a catalogue smoked PC diffuser.
  - Roughly $1.5-5/m (3rd-party listings).
  - Ship bulk to a 3PL by sea or air freight.
- **End cap, up to about 200 units:** MJF/SLA prints from JLC3DP.
- **End cap, about 200-500 units:** a Protolabs aluminum mould (from about $1,500, published) is worth getting a quote for.
- **Shipping:** the 2-piece rail keeps the retail box under 48 in, so there is no Additional Handling.

**(c) 1,000+ units**
- **Rail:** custom aluminum extrusion.
  - Die about $400-4,000 (Gabrian / AEC published ranges); MOQ about 1,000-2,000 lb per shape (AEC).
  - The custom profile can integrate the diffuser groove, splice channel, cable path and soft-foot slots.
- **Diffuser:** a catalogue smoked PC/PMMA diffuser, or a custom co-extrusion if the profile needs it (die cost unverified).
- **End cap:** injection mould it.
  - An aluminum or P20 single-cavity mould (about $1,500-12,000 across published and 3rd-party ranges) is enough for this volume.
  - Get 3 or more quotes: Protolabs, Fictiv/Xometry, and a China moulder.
- **Shipping:** keep the 2-piece rail so it ships as a standard parcel.

---

## 4. URL list (checked 2026-11-28)

"Opened" means WebFetch returned page content. "Search only" means the information came from search-engine excerpts of that URL.

| URL | Opened? |
|---|---|
| https://www.gabrian.com/cost-of-custom-aluminum-extrusions/ | Yes |
| https://aec.org/sites/default/files/2022-11/bcwhitepaper_rev01252019.pdf | Yes (PDF text extracted) |
| https://jlc3dp.com/capabilities/3d-printing-service | Yes |
| https://jlc3dp.com/help/article/3d-printing-design-guideline | Yes |
| https://jlc3dp.com/blog/drastic-material-price-cuts-and-adjusted-post-processing-service-fees | Yes |
| https://3D.jlcpcb.com/help/article/200-PA12-HP-Nylon | Search only |
| https://www.shapeways.com/ | Yes |
| https://3dprint.com/314952/shapeways-relaunched-with-all-assets-under-one-roof/ | Search only |
| https://www.protolabs.com/en-gb/services/3d-printing/3d-printing-maximum-extents/ | Yes |
| https://www.protolabs.com/resources/blog/aluminum-mold-tooling-for-injection-molding/ | Yes |
| https://www.protolabs.com/resources/design-tips/11-tips-to-reduce-injection-molding-costs/ | Yes |
| https://www.protolabs.com/resources/blog/aluminum-vs-steel-tooling/ | Search only |
| https://www.xometry.com/resources/injection-molding/injection-molding-cost/ | Yes |
| https://support.xometry.com/hc/en-us/articles/216286528-What-s-the-maximum-size-of-a-part-you-can-print-} | Search only |
| https://xometry.com/capabilities/3d-printing-service/large-scale | Search only |
| https://www.xometry.com/resources/machining/ways-save-money-cnc-prototypes/ | Search only |
| https://www.xometry.com:443/capabilities/plastic-extrusion-services | Search only |
| https://www.fictiv.com/articles/steel-vs-aluminum-for-injection-molds | Yes |
| https://hubs.com/knowledge-base/how-much-does-injection-molding-cost | Yes |
| https://pcbway.com/rapid-prototyping/injection-molding/ | Yes |
| https://www.pcbway.com/rapid-prototyping/3d-printing/3d-printing-FDM.html | Search only |
| https://www.pcbway.com/rapid-prototyping/3d-printing/3d-printing-SLS.html | Search only |
| https://jlccnc.com/ | Search only |
| https://jlccnc.com/news/price-adjustment-in-may-2026 | Search only |
| https://craftcloud3d.com/en/p/3d-printing-services | Search only |
| https://all3dp.com/1/uncover-real-3d-printing-service-costs/ | Search only |
| https://www.treatstock.com/c/the-tech-deck-llc?ln=en-US | Search only |
| https://www.superbrightleds.com/pds-4-plus-extrusion | Yes (partly truncated) |
| https://www.mr-resistor.co.uk/product/24651 | Search only |
| https://www.walmart.com/c/kp/led-channel-diffuser | Search only |
| https://www.desertcart.us/products/38675704-muzata-10pack-3-3ft-1m-led-channel-aluminum-u-shape.md | Search only |
| https://www.alibaba.com/product-introduction/toco-Aluminium-Led-Profile-Black-Led_1600089463826.html | Search only |
| https://www.alibaba.com/product-introduction/U-V-Shape-Channel-Aluminum-LED_1600524934007.html | Search only |
| https://www.alibaba.com/product-introduction/OEM-Factory-Customized-Led-Extrusion-Profiles_1601153026887.html | Search only |
| https://get-it-made.co.uk/resources/how-much-does-aluminium-extrusion-cost | Search only |
| https://www.slideshare.net/slideshow/taber-extrusions-sales-presentation/161607723 | Search only |
| https://www.steel-technology.com/products/bonnell-aluminum/custom-aluminum-extrusions | Search only |
| https://www.mfgrobots.com/Article/mfg/it/54227.html | Search only |
| https://www.unionfab.com/blog/2026/03/jlc-vs-pcbway-vs-rapiddirect-vs-unionfab | Search only |
| https://www.ups.com/us/en/support/shipping-support/shipping-dimensions-weight/avoid-additional-shipping-fees | **No** (Access Denied); search only |
| https://www.ups.com/assets/resources/media/en_US/additional_charges_daily.pdf | **No** (blocked); search only |
| https://www.ups.com/assets/resources/media/en_US/additional_charges_retail.pdf | Search only |
| https://assets.ups.com/adobe/assets/urn:aaid:aem:bbf2553c-15e5-4b2d-abcd-b7445b13daa0/original/as/small-business-rate-guide-us-en.pdf | **No** (blocked); search only |
| https://www.fedex.com/content/dam/fedex/us-united-states/services/Service_Guide_2026.pdf | **No** (permission error); search only |
| https://www.fedex.com/en-us/customer-support/faqs/business/surcharges-and-fees/what-is-an-oversize-charge.html | **No** (permission error); search only |
| https://www.easyship.com/blog/ups-surcharges | Search only (3rd-party) |

---

## 5. Could not verify

- **Actual instant-quote prices** for the 60x30x15 mm end cap and for a rail segment at JLC3DP, PCBWay, Craftcloud, Shapeways, Xometry, Protolabs, Treatstock, JLCCNC and PCBWay CNC. Every one needs a CAD upload, an account, or both. The per-cap figures above are estimates from JLC's published $/g rate. JLC's July 2026 pricing update could not be read.
- **Injection moulding:** no published dollar figures on the Fictiv, ICOMold, Rex Plastics (site not reached) or JLC/JLCMC pages. No per-part price for any moulder.
- **Bonnell and Taber:** no die charge or MOQ published. Taber's "no minimum" claim comes from an old, undated deck.
- **Custom PC/PMMA diffuser extrusion die cost:** not found anywhere.
- **Per-metre prices:**
  - Klus PDS4 black anodised: not found.
  - Exact single Muzata black SKU: not found.
  - Alibaba listing prices are sample or marketing prices, not quotes.
- **Shipping:** dollar amounts for UPS/FedEx length-based Additional Handling. Also whether UPS's 40 lb minimum billable weight applies to length-triggered AH at retail or daily rates; the snippet was ambiguous.
- **Official carrier pages:** none of the UPS/FedEx pages could be opened from this environment. Thresholds come from search excerpts of those official URLs, corroborated by 3rd parties.
- **Shapeways:** it is operating, but it does not publish build sizes. Whether its US entity and domain have been fully resolved is unclear.
- **Non-US carriers** (Royal Mail, DHL, Canada Post) were not checked.
