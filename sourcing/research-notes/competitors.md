# Competitor scan: LED strips / light guides over piano keys

Checked 2026-11-28. Every fact has a URL after it. In this file:
- **[fetched]** means I opened the page and read it.
- **[snippet]** means the fact comes only from a search-result summary, because the page blocked fetching or I did not open it.
- **unverified** means I could not confirm it from any source.

Product context: an ESP32 + WS2812B 144/m strip of about 1.25 m, priced about $60-80. It serves its own Wi-Fi page for MIDI upload, works on acoustic pianos, and will add an I2S mic later.

---

## 1. Entries

### A. Direct competitors: add-on strips for an existing piano

#### 1. Piano LED Plus (2026 version)
- **Maker:** Piano LED, a French start-up. The app developer is listed as "Piano LED Inc." [fetched] https://apps.apple.com/us/app/piano-led-app/id6468573666 ; "French tech start up" [fetched] https://eftm.com/2023/01/effortlessly-learn-piano-with-lights-230847
- **Type:** Commercial.
- **Price:**
  - Starter kit "Essentiel": €169, a Black Friday price down from €199. It includes 50 songs and no subscription.
  - "Virtuoso": €239, down from €298. It includes 1 year of subscription and 5,000+ songs, then €99/yr.
  - The page shows EUR only and no USD price. [fetched] https://pianoledshop.com/products/pianoledplus and https://www.pianoledshop.com/en
  - Bundles with Woodbrass digital pianos run €329-€599. [fetched] https://www.pianoledshop.com/en/collections/our-packs
  - A 2023 CES write-up quoted "~$460". [fetched] https://eftm.com/2023/01/effortlessly-learn-piano-with-lights-230847
- **Needs MIDI/USB:** Yes. It connects over USB-B ("USB to Host"), which is the cable included, or over 5-pin MIDI, which needs a MIDI cable and a micro-USB adapter that you buy separately. The app talks to the box over Bluetooth/Wi-Fi. The page claims latency under 20 ms. [fetched] https://pianoledshop.com/products/pianoledplus
- **Acoustic piano:** No. The page says it "does not work with acoustic pianos". [fetched] https://www.pianoledshop.com/en
- **Mounting:**
  - The strip has an integrated adhesive. The control box is held by magnets included in the kit. [fetched] https://pianoledshop.com/products/pianoledplus
- **Strip specs:**
  - 123 x 1.3 x 0.4 cm, can be cut to length, in black or white. [fetched] https://pianoledshop.com/products/pianoledplus
  - WS2812B, 144 LEDs/m, about 48 in. [snippet] Marketing PDF: https://cdn-assets.inwink.com/094dd8fe-6acf-40d8-aea1-fbfbc95cf9a4/259b93c7-94f7-435d-81ce-76bc047d18bb
  - This is the same LED spec as our product.
- **Where sold:**
  - https://pianoledshop.com (ships to the US, with express delivery estimated at about 5 days). [fetched] https://pianoledshop.com
  - Focus Camera used to list it, but that URL now 301-redirects to an empty category page. [fetched] https://www.focuscamera.com/pro-audio/piano-led-plus-synthesia-piano-learning-software-compatible-learning-system-with-led-strip.html
- **Buyer complaints:**
  - **On-site product reviews** [fetched] https://pianoledshop.com/products/pianoledplus
    - LEDs are not well centred on the keys, or a few keys are misaligned (several reviewers).
    - Reconnecting is needed on each use, and switching between phones is a struggle.
    - The app crashes at launch and needs a reset.
    - The magnet patch did not hold the control box, and the box covered the strip.
    - Blue LEDs are too dark in daylight.
    - The app is limited without a subscription.
    - One buyer got 38 free songs instead of the advertised 50.
  - **Trustpilot**: 4.3 from 258 reviews, with 12% 1-star. [fetched] https://au.trustpilot.com/review/pianoledshop.com
    - The wrong keys light up when several keys are played. "Does not work as advertised."
    - The strip is too long for a Roland FP-10.
    - Support asked the reviewer for a positive review.
    - A lost or late package.
    - Synthesia support was reportedly dropped.
    - The app is buggy, logs the user out repeatedly, and reverts to French.
    - Features are behind a paywall, and there is no RTP-MIDI or open standard support.
    - Support answers only in French.
    - Returns are costly because of import taxes.
  - **iOS App Store**: 3.3★ from 12 ratings. "you have to set it up everytime you turn the device on"; the strip fails to power on and loses signal. [fetched] https://apps.apple.com/us/app/piano-led-app/id6468573666

#### 2. The ONE Piano Hi-Lite (model TOH1)
- **Maker:** The ONE Music Group, The ONE Smart Piano. [fetched] https://store.momschoiceawards.com/product/7338
- **Type:** Commercial, originally crowdfunded on Indiegogo.
  - Indiegogo pledges started at US$199. [fetched] https://newatlas.com/one-piano-hi-lite-led-learning-strip/51421/
  - Another source says "from USD$179 on Indiegogo". [snippet] https://www.stuff.tv/?p=727200
- **Price:**
  - $269.99 MSRP. [fetched] https://store.momschoiceawards.com/product/7338
  - $229 per a 2018 Gizmodo Japan article. [fetched] https://www.gizmodo.jp/2018/01/piano-hi-lite-the1.html
  - **Current price: unverified.**
    - The Amazon listing exists (B075XLPBQT) [snippet] https://www.amazon.com/ONE-Music-Group-Beginners-TOH1/dp/B075XLPBQT, but it returned HTTP 503 when fetched.
    - The official product URL https://theonemusic.com/products/the-one-piano-hi-lite loaded a storefront page with no Hi-Lite listing [fetched]. It may be discontinued, which is unverified.
    - Ubuy lists it as out of stock. [snippet] https://www.ubuy.com.ph/product/D0XZ85I-the-one-music-group-player-piano-toh1
- **Needs MIDI/USB:** No MIDI from the piano. The strip connects by micro-USB to a phone or tablet running The ONE app. [fetched] https://newatlas.com/one-piano-hi-lite-led-learning-strip/51421/
  - The Amazon listing mentions "sensors, LED indicators and Bluetooth 4.0". [snippet] https://www.amazon.com/ONE-Hi-Lite-Learning-System-Beginner/dp/B075XLPBQT
  - It works with Synthesia and MIDI files. [fetched] https://store.momschoiceawards.com/product/7338
- **Acoustic piano:** Yes, claimed: "any 88-key piano or keyboard". [fetched] https://store.momschoiceawards.com/product/7338
  - Key presses are detected by laser ("ユーザーの打鍵はレーザーで検知される"). [fetched] https://www.gizmodo.jp/2018/01/piano-hi-lite-the1.html
  - **This is the only commercial strip found that claims acoustic support with key detection.**
- **Mounting:** It rests on the keys or the key slip, with no installation. It works on 88-key instruments only. [fetched] https://store.momschoiceawards.com/product/7338 ; https://www.gizmodo.jp/2018/01/piano-hi-lite-the1.html
- **Where sold:** Amazon (listing above), and resellers including Muziker [snippet] https://www.muziker.ee/smart-piano-the-one-piano-hi-lite and desertcart.
- **Buyer complaints:** These are desertcart mirror reviews of the Amazon listing. Desertcart returned 403, so this is [snippet] only. https://www.desertcart.sg/products/70158941-the-one-music-group-hi-lite-88-keys-led-light
  - "could not get it to connect to my smart devices"
  - The cable connection also failed, and the buyer got a refund.
  - "size doesn't fit all Pianos, software is not intuitive"
  - "works when you position the bar on the keyboard correctly"
  - Review of the wider ONE line: the driver has not been updated. [snippet] https://www.engadget.com/2018-11-27-one-smart-piano-learn-to-play.html

#### 3. KEEZI (with the optional KEENEKT adapter)
- **Maker:** KEEZI. Company location unverified. [fetched] https://keezishop.com/
- **Type:** Commercial.
- **Price:** $149.99, a sale price down from $199.99, and marked "Sold out". The KEEZI + KEENEKT bundle is $199.49, and a BLACKFRIDAY15 code takes $15 off it. [fetched] https://keezishop.com/products/keezi
- **Needs MIDI/USB:** Mostly. It connects with the included USB-A to USB-B cable, or a MIDI-to-USB adapter for 5-pin pianos. It has a built-in touchscreen, with no app and no subscription. KEENEKT is only needed to connect to a PC or tablet for Synthesia or Ableton. [fetched] https://keezishop.com/
- **Acoustic piano:** Partial.
  - "Acoustic pianos get the LED lighting, scales, chords, and animations." Visualizer, Easy Chords and Arpeggiator need MIDI. There is no note detection. [fetched] https://keezishop.com/
  - The product page itself says only that it "works with virtually all digital pianos and keyboards that support MIDI". [fetched] https://keezishop.com/products/keezi
- **Mounting:** An "LED mounting kit" is included, of an unspecified type. The strip can be cut to fit 25-88 keys. [fetched] https://keezishop.com/products/keezi
- **Where sold:** https://keezishop.com
- **Buyer complaints:** None found. There are no reviews on site, and no third-party reviews turned up. Unverified.

#### 4. i-Piano MIDI LED Visualizer (Models U / U88 / T88W)
- **Maker:** An Etsy seller, i-Piano. Seller identity and location are unverified, because Etsy returned 403 to every fetch.
- **Type:** Commercial, small-batch and built to order.
- **Price:**
  - $169 for an 88-key black strip. [snippet] https://www.etsy.com/listing/4414570478/i-piano-midi-led-visualizer
  - eBay US $149.00 (T88W), out of stock. [snippet] https://ebay.com/itm/126238927003 (403 on fetch)
  - eBay.de listing for U88. [snippet] https://www.ebay.de/itm/127178769699 (403)
- **Needs MIDI/USB:** Yes. It is USB-powered and plug-and-play with MIDI pianos and "fully compatible with Synthesia". The Model-U "always need[s] to be connected to a computer". [snippet] https://elearn.nptel.ac.in/products/i-piano-reactive-led-visualizer-self-tutor-for-midi-pianos-u/12439975 (an odd mirror site, low trust)
  - It has a tutor mode where "the next key ... will light up and wait". [snippet] https://www.etsy.com/listing/4414570478/i-piano-midi-led-visualizer
- **Acoustic piano:** No (MIDI pianos only). [snippet] same.
- **Mounting:** Unverified. Each unit is custom-built to the buyer's piano brand, model and key count. [snippet] https://www.etsy.com/in-en/listing/1334255377/i-piano-led-visualizer-light-strip
- **Buyer complaints:** Unverified, because Etsy reviews could not be fetched.

#### 5. PianoMaestro light strip (legacy)
- **Maker:** Unverified.
- **Type:** Commercial, legacy.
- **Price:** Unverified.
- **Needs MIDI/USB:** It connects to a PC over USB. Wait mode needs connections between device, piano and PC. [snippet] search summary, no primary page found.
- **Acoustic piano:** Lights only. The strip is described as sitting on the black keys of any acoustic or digital piano. [snippet] (as cited above)
- **Mounting:** A 48-light, ruler-like strip laid on the black keys. [snippet]
- **Buyer complaints (user review, via snippet):**
  - Colours are fixed: green for white keys, red for black keys.
  - It works best with Synthesia rather than its own software.
  - The Windows driver freezes the lights.
- **Source note:** No primary URL could be verified, so treat this whole entry as low confidence. A forum mention of "the PianoMaestro light strip" is at [snippet] https://www.synthesiagame.com/forum/viewtopic.php?p=42684

### B. Crowdfunding

#### 6. Pianissimo: "Piano learning, reimagined" (Kickstarter)
- **Maker:** drvelazquez (Marlborough, New Zealand). [snippet] https://www.kicktraq.com/projects/drvelazquez/pianissimo-piano-learning-reimagined/ (fetched page showed only a site-outage notice)
- **Type:** Crowdfunding.
  - Funded. Kicktraq showed 40 backers and ">400%" funding. [snippet] same URL.
  - Launched on Product Hunt in 2026. [fetched] https://www.producthunt.com/posts/pianissimo-piano-learning-reimagined
- **Price:** Unverified.
- **Needs MIDI/USB:** It receives MIDI files over Bluetooth and shows falling-note "Guitar Hero" lights. The page does not say whether it reads the keyboard. [fetched] https://www.producthunt.com/posts/pianissimo-piano-learning-reimagined
- **Acoustic piano:** Unverified. The page says "any keyboard".
- **Mounting:** It "sits on top of" the keyboard. The build is an Arduino Uno driving a WS2813B strip. [snippet] https://forum.arduino.cc/t/i-made-a-guitar-hero-device-to-learn-how-to-play-piano-and-it-was-a-success/1435020 (HTTP 429 on fetch)
- **Buyer complaints:** None. Product Hunt shows no reviews yet.

#### 7. The ONE Piano Hi-Lite on Indiegogo
See entry 2. The Indiegogo page fetched as empty.

### C. Open-source / DIY

#### 8. Piano LED Visualizer (onlaj)
- **Maker:** Aleksander "Onlaj". [snippet] https://github.com/sponsors/onlaj
- **Type:** Open-source. 790 stars and 160 forks at fetch time. [fetched] https://github.com/onlaj/Piano-LED-Visualizer
- **Price:** Free software. Parts cost "75-100 USD" excluding piano and tablet. There is no pre-built kit. [fetched] https://github.com/onlaj/Piano-LED-Visualizer
- **Hardware:** Raspberry Pi Zero WH, plus a WS2812B strip of at least 1.5 m at 144/m, plus a 5V 6A supply. [fetched] https://github.com/onlaj/Piano-LED-Visualizer
- **Needs MIDI/USB:** Yes: MIDI or USB output, or a MIDI-USB interface. It has Synthesia integration and a web UI on port 80. [fetched] same.
- **Acoustic piano:** No.
- **Mounting:** Double-sided tape, with an optional aluminium profile and diffuser plus a 3D-printed case. [fetched] same.
- **Complaints (from its own docs):**
  - Pi models other than the Zero show key-to-light lag.
  - Cheap MIDI interfaces are unreliable. [fetched] same.
  - A builder notes 172 LEDs can draw more than 5 A. [fetched] https://yanniznik.com/building-a-led-piano-visualizer/
  - Issue tracker: https://www.github.com/onlaj/Piano-LED-Visualizer/issues (not opened).
- **Forks/derivatives:**
  - pyanoled. [snippet] https://pypi.org/project/pyanoled
  - Forks by nisaev, cmxl, and SirLefti. [snippet] https://github.com/nisaev/Piano-LED-Visualizer
  - Tom's Hardware build guide. [snippet] https://www.tomshardware.com/how-to/build-piano-led-trip-raspberry-pi (the fetch returned no body)

#### 9. Pianethor (battiemme): closest open-source match to our product
- **Maker:** battiemme. Created 2026-04-23. [fetched] https://hackaday.io/project/205563-pianethor
- **Type:** Open-source, AGPL-3.0, 8 stars. [fetched] https://github.com/battiemme/Pianethor
- **Price:** Unverified. The project lists parts only.
- **Hardware:** ESP32 (CH340C) + WS2812B 5V 74/m (72 LEDs) + an **optional INMP441 I2S mic** + a 5V power bank. [fetched] https://github.com/battiemme/Pianethor
- **Wi-Fi:** The ESP32 runs its own access point "Pianethor" serving a web UI at 192.168.4.1. The UI does MIDI file upload, track and colour selection, transpose, and speed from 10-150%. **This is essentially the same architecture as our product.** [fetched] same.
- **Needs MIDI from the piano:** No. You upload MIDI files (under 100 KB, about 900 notes max). [fetched] same.
- **Acoustic piano:** Yes. With the mic it advances when it hears sound. It uses volume thresholds that need tuning per room, and does not do pitch detection. [fetched] same.
- **Mounting:** Removable adhesive strap. The lowest LED sits on the lowest C. [fetched] same.
- **Complaints:** None public found.

#### 10. PianoLights (state-of-the-art)
- **Type:** Open-source, 13 stars. [fetched] https://github.com/state-of-the-art/PianoLights
- **Price:** About $40 in parts. [fetched] same.
- **Hardware:** ESP32 + a MAX3421E USB host shield + WS2812B 144/m (176 LEDs, 2 per key). [fetched] same.
- **Needs MIDI/USB:** Yes. It is a USB-MIDI to BLE-MIDI proxy for Synthesia on Android. [fetched] same.
- **Acoustic piano:** No.
- **Mounting:** Aluminium LED channel with a diffuser, and the boards held with double tape. [fetched] same.

#### 11. PianoLux ESP32 (serifpersia, fork by vlsim)
- **Type:** Open-source. [fetched] https://github.com/vlsim/pianolux-esp32
  - The original repo, serifpersia/pianolux-esp32, was not opened.
  - serifpersia/pianoled-arduino and serifpersia/pianoled both returned 404.
- **Hardware:** ESP32-S2/S3 as a USB host, or any Wi-Fi ESP32 using RTP-MIDI. BLE-MIDI is "very experimental". [fetched] same.
- **Web UI:** Hosted at 192.168.4.1, with LED modes, an 88-key on-screen keyboard, and OTA updates. No file-upload or learning mode is documented. [fetched] same.
- **Acoustic piano:** No.
- **Mounting:** Not documented.

#### 12. PianoLED (Nicolás de Ory, PCBWay) and marvinscham/pianoled-arduino
- **Type:** Open-source PCB project, 2019-07-24. [fetched] https://www.pcbway.com/project/shareproject/PianoLED___Light_up_the_notes_as_you_play.html
  - Related repo [snippet]: https://github.com/marvinscham/pianoled-arduino
- **Hardware:** Arduino + optoisolated 5-pin MIDI in + 74 WS2812B. [fetched] same.
- **Needs MIDI/USB:** Yes (5-pin MIDI).
- **Acoustic piano:** No.
- **Mounting:** Not specified.

#### 13. LightSync MIDI (ElectronicWings)
- **Date:** 2024-07-10. [fetched] https://www.electronicwings.com/users/YogarathinamTL/projects/4351/lightsync-midi---interactive-led-learning-tool-for-electonic-keyboards-and-piano
- **Hardware:** ESP32 WROOM + WS2812B 144 LEDs. [fetched] same.
- **Needs MIDI/USB:** Yes. It runs from a PC Python app over USB MIDI, and works with Synthesia and DAWs. [fetched] same.
- **Acoustic piano:** No.

#### 14. Other DIY projects (not opened, [snippet] only)
- Instructables "LED Piano Learning Strip". The fetch returned the title only, so its details are unverified. https://www.instructables.com/LED-Piano-Learning-Strip
- touchgadget/key_led. Notes that a 1 m strip is too short for 88 keys. [snippet] https://github.com/touchgadget/key_led
- Raspberry Pi Pico W "Pico Piano Helper" (Adrian Cruceru). The fetch returned 403. https://www.hackster.io/news/adrian-cruceru-s-pico-piano-helper-uses-micropython-on-a-raspberry-pi-pico-w-to-teach-you-a-new-tune-45d8938c682a
- "Rousseau" Pi Zero LED piano visualiser. https://www.raspberrypi.com/news/rousseau-raspberry-pi-zero-led-piano-visualiser/
- Adafruit MIDI NeoPixel visualizer. https://learn.adafruit.com/midi-neopixel-visualizer/overview
- Hackaday "MIDI Hi-Lites". https://hackaday.io/project/11284-midi-hi-lites
- UIUC ECE445 student LED piano trainer spec with optional mic input for acoustic pianos. https://courses.grainger.illinois.edu/ece445/getfile.asp?id=25484

### D. Adjacent: light-up keyboards (replace the piano rather than add to it)

#### 15. ROLI Piano (49 keys) and LUMI Keys
- **ROLI Piano:**
  - 49 full-size illuminated keys, USB/BLE MIDI. [fetched] https://roli.com/us/product/piano-learn
  - Price: $599 regular, $399 introductory at launch in January 2025. [snippet] https://www.soundonsound.com/news/roli-launch-roli-piano-system
  - Current price unverified, because the page showed no price.
- **LUMI Keys Studio Edition (24 keys):** Launched at $299. [snippet] https://musicradar.com/news/rolis-lumi-keys-studio-edition-promises-mpe-control-with-a-standard-midi-keyboard-action
  - The current roli.com page shows ROLI Piano M instead and lists no price. [fetched] https://www.roli.com/products/blocks/lumi-keys-studio-edition
- **Acoustic piano:** Not applicable (these are keyboards).

#### 16. PopuPiano (PopuMusic)
- 29-key portable smart MIDI keyboard with LED keys. [fetched] https://www.stacksocial.com/sales/popupiano-smart-portable-keyboard-piano-with-chord-pad-black
- Price: $268.99 deal, MSRP $399. [fetched] same.
- A 59-key bundle is $314.97 on a deal site. [snippet] https://deals.newatlas.com/sales/popupiano-smart-portable-59-key-midi-keyboard-chord-pad-speaker-pedal-black
- Complaints: one review, no text shown.

#### 17. The ONE Smart Piano / Light keyboards
- TheONE Sing Smart Piano from $299 (down from $459). TOP1X from $959. [fetched] https://theonemusic.com/products/the-one-piano-hi-lite (storefront content)
- Critique: lights help you play but not understand. [snippet] https://www.engadget.com/2018-11-27-one-smart-piano-learn-to-play.html

#### 18. Gemini PianoProdigy GPP-101
- 24-key RGB light-up BLE-MIDI keyboard, expandable to 72 keys. $102.49 at Staples. [snippet] https://www.staples.com/gemini-pianoprodigy-expandable-24-key-bluetooth-midi-learning-keyboard-with-light-up-keys-gpp-101/product_24621202 (403 on fetch)

#### Not found
- **"McMusic":** No product by this name was found. The closest match is the McCarthy Music Illuminating Piano, an old 61-key lit keyboard. [snippet] https://www.tomsguide.com/us/mccarthy-illuminating-piano,news-20887.html
- **Kmise and generic Amazon/AliExpress strips:** No generic "piano LED learning strip" listing was found on Amazon or AliExpress in several searches. Only the Hi-Lite showed up on Amazon. Amazon fetches returned 503.
- **"LED Piano" iOS app (developer Duc Tai Truong, Vietnam):** It pairs over Bluetooth with an unnamed add-on light system on the keys. It has 3.0★ from 1 rating, and the reviewer complains about a poor song library, no favourites, and no connection guidance. [fetched] https://apps.apple.com/us/app/led-piano/id6444875266
  - This suggests an unbranded Asian strip product exists. Its name is unverified.

---

## 2. Market observations

**Price bands**
- **DIY:** about $40 (PianoLights) and $75-100 (onlaj) in parts, plus significant build skill.
- **Small-batch / indie:** i-Piano $149-169, KEEZI $149.99 (sold out).
- **Established commercial strip:** Piano LED Plus €169-239, plus a €99/yr subscription after year 1, and about $460 quoted in 2023. Hi-Lite MSRP was $269.99, with current availability unclear.
- **Light-up keyboards:** about $100 (Gemini), $269-399 (PopuPiano, LUMI, ROLI), and $299+ (The ONE).
- **Implication:** A $60-80 finished product would undercut every commercial strip by about 2x and come close to the DIY parts cost.

**Biggest gap: acoustic pianos**
- Piano LED Plus, i-Piano and all MIDI-based DIY projects explicitly need USB or MIDI.
- KEEZI on acoustic is lights only.
- The only commercial acoustic-capable strip (Hi-Lite) is old, $229-270, 88-key only, and appears hard to buy now.
- **Pianethor** (an AGPL ESP32 project from April 2026) already does:
  - an ESP32 access point with a web MIDI upload page
  - WS2812B
  - an optional I2S mic for acoustic advance
  It is not sold commercially, but it shows the core idea is not novel at the hobbyist level. Differentiation will need to come from polish, price, packaging, mounting, and better mic detection (Pianethor uses amplitude thresholds only, not pitch).

**IP note**
- US Patent 11,087,636 ("Lights-guided piano learning and teaching apparatus", issued 2021-08-10) describes a microphone listening for the expected note to advance lights. [snippet] https://patents.justia.com/patent/11087636 (403 on fetch)
- Assignee and claims are unverified. Worth a freedom-to-operate check before shipping mic-based "wait for note".

**Common complaints across products**
1. **LED-to-key alignment.** Strips don't line up with keys (Piano LED Plus reviews and Trustpilot), and length doesn't fit some pianos (Hi-Lite, Roland FP-10). A 144/m strip is about 6.9 mm pitch against about 23.5 mm per white key, so mapping and calibration UX matter.
2. **Connection and setup reliability.** Re-pairing every session (Piano LED app, Trustpilot), and Hi-Lite failing to connect to phones. Our self-hosted Wi-Fi AP avoids app pairing but adds its own Wi-Fi/captive-portal friction.
3. **App quality and lock-in.** Buggy apps, paywalled features, a dropped Synthesia integration, and no open standards.
4. **Mounting.** The magnet patch fails, and the box covers the strip.
5. **Visibility.** Blue LEDs are too dim in daylight.
6. **Support and language.** French-only support from Piano LED, and costly international returns. A US-based seller is an advantage.
7. **Pedagogy skepticism.** Lights are seen as a "crutch" or "gimmick". [snippet] https://ask.metafilter.com/195093/Do-light-up-keyboards-help-learning-piano

---

## 3. URLs used (all checked 2026-11-28)

| URL | Opened? |
|---|---|
| https://pianoledshop.com/products/pianoledplus | Yes |
| https://pianoledshop.com | Yes |
| https://www.pianoledshop.com/en | Yes |
| https://www.pianoledshop.com/en/collections/our-packs | Yes |
| https://www.pianoledshop.com/en/products/pack-piano-pianoled | No (404) |
| https://au.trustpilot.com/review/pianoledshop.com | Yes |
| https://apps.apple.com/us/app/piano-led-app/id6468573666 | Yes |
| https://eftm.com/2023/01/effortlessly-learn-piano-with-lights-230847 | Yes |
| https://armdevices.net/?p=138722 | Yes (no price info) |
| https://www.focuscamera.com/pro-audio/piano-led-plus-synthesia-piano-learning-software-compatible-learning-system-with-led-strip.html | Redirected (301) to an empty category |
| https://www.focusproaudio.com/collections/practice-learning-equipment | Yes (no products) |
| https://cdn-assets.inwink.com/094dd8fe-6acf-40d8-aea1-fbfbc95cf9a4/259b93c7-94f7-435d-81ce-76bc047d18bb | Not opened (snippet) |
| https://store.momschoiceawards.com/product/7338 | Yes |
| https://newatlas.com/one-piano-hi-lite-led-learning-strip/51421/ | Yes |
| https://www.gizmodo.jp/2018/01/piano-hi-lite-the1.html | Yes |
| https://www.amazon.com/ONE-Music-Group-Beginners-TOH1/dp/B075XLPBQT | No (503) |
| https://www.amazon.com/ONE-Hi-Lite-Learning-System-Beginner/dp/B075XLPBQT | No (503) |
| https://www.desertcart.sg/products/70158941-the-one-music-group-hi-lite-88-keys-led-light | No (403), snippet used |
| https://theonemusic.com/products/the-one-piano-hi-lite | Yes (storefront, no Hi-Lite) |
| https://theonemusic.com/blogs/knowledge/led-piano-teaching-system-learn-piano-by-following-the-lights-june-2026 | Yes |
| https://www.theonesmartpiano.com/ | Yes (Thai site, no Hi-Lite) |
| https://www.bhphotovideo.com/c/product/1352419-REG/the_one_the_one_smart_piano_strip_smart_piano_strip.html | No (403) |
| https://www.indiegogo.com/projects/the-one-piano-hi-lite-88-key-piano-tutor-system | Yes, but empty |
| https://www.stuff.tv/?p=727200 | Not opened (snippet) |
| https://www.ubuy.com.ph/product/D0XZ85I-the-one-music-group-player-piano-toh1 | Not opened (snippet) |
| https://www.muziker.ee/smart-piano-the-one-piano-hi-lite | Not opened (snippet) |
| https://www.engadget.com/2018-11-27-one-smart-piano-learn-to-play.html | Not opened (snippet) |
| https://keezishop.com/ | Yes |
| https://keezishop.com/products/keezi | Yes |
| https://www.etsy.com/listing/4414570478/i-piano-midi-led-visualizer | No (403), snippet |
| https://www.etsy.com/dk-en/listing/1362438541/i-piano-midi-led-visualizer | No (403) |
| https://www.etsy.com/listing/1334255377/i-piano-led-visualizer-light-strip | No (403), snippet |
| https://ebay.com/itm/126238927003 | No (403), snippet |
| https://www.ebay.de/itm/127178769699 | No (403) |
| https://elearn.nptel.ac.in/products/i-piano-reactive-led-visualizer-self-tutor-for-midi-pianos-u/12439975 | Not opened (snippet) |
| https://www.synthesiagame.com/forum/viewtopic.php?p=42684 | Not opened (snippet) |
| https://www.kicktraq.com/projects/drvelazquez/pianissimo-piano-learning-reimagined/ | Yes, but outage notice only; snippet used |
| https://www.producthunt.com/posts/pianissimo-piano-learning-reimagined | Yes |
| https://forum.arduino.cc/t/i-made-a-guitar-hero-device-to-learn-how-to-play-piano-and-it-was-a-success/1435020 | No (429), snippet |
| https://github.com/onlaj/Piano-LED-Visualizer | Yes |
| https://github.com/sponsors/onlaj | Not opened (snippet) |
| https://yanniznik.com/building-a-led-piano-visualizer/ | Yes |
| https://www.tomshardware.com/how-to/build-piano-led-trip-raspberry-pi | Yes, but no body returned |
| https://pypi.org/project/pyanoled | Not opened |
| https://github.com/nisaev/Piano-LED-Visualizer | Not opened |
| https://hackaday.io/project/205563-pianethor | Yes |
| https://github.com/battiemme/Pianethor | Yes |
| https://github.com/state-of-the-art/PianoLights | Yes |
| https://github.com/vlsim/pianolux-esp32 | Yes |
| https://github.com/serifpersia/pianoled-arduino | No (404) |
| https://github.com/serifpersia/pianoled | No (404) |
| https://github.com/marvinscham/pianoled-arduino | Not opened |
| https://www.pcbway.com/project/shareproject/PianoLED___Light_up_the_notes_as_you_play.html | Yes |
| https://www.electronicwings.com/users/YogarathinamTL/projects/4351/lightsync-midi---interactive-led-learning-tool-for-electonic-keyboards-and-piano | Yes |
| https://www.instructables.com/LED-Piano-Learning-Strip | Yes, but title only |
| https://github.com/touchgadget/key_led | Not opened (snippet) |
| https://www.hackster.io/news/adrian-cruceru-s-pico-piano-helper-uses-micropython-on-a-raspberry-pi-pico-w-to-teach-you-a-new-tune-45d8938c682a | No (403) |
| https://www.raspberrypi.com/news/rousseau-raspberry-pi-zero-led-piano-visualiser/ | Not opened |
| https://learn.adafruit.com/midi-neopixel-visualizer/overview | Not opened |
| https://hackaday.io/project/11284-midi-hi-lites | Not opened |
| https://courses.grainger.illinois.edu/ece445/getfile.asp?id=25484 | Not opened (snippet) |
| https://patents.justia.com/patent/11087636 | No (403), snippet |
| https://roli.com/us/product/piano-learn | Yes (no price) |
| https://www.roli.com/products/blocks/lumi-keys-studio-edition | Yes (shows Piano M, no price) |
| https://www.soundonsound.com/news/roli-launch-roli-piano-system | Not opened (snippet) |
| https://musicradar.com/news/rolis-lumi-keys-studio-edition-promises-mpe-control-with-a-standard-midi-keyboard-action | Not opened (snippet) |
| https://www.stacksocial.com/sales/popupiano-smart-portable-keyboard-piano-with-chord-pad-black | Yes |
| https://deals.newatlas.com/sales/popupiano-smart-portable-59-key-midi-keyboard-chord-pad-speaker-pedal-black | Not opened (snippet) |
| https://www.staples.com/gemini-pianoprodigy-expandable-24-key-bluetooth-midi-learning-keyboard-with-light-up-keys-gpp-101/product_24621202 | No (403), snippet |
| https://www.tomsguide.com/us/mccarthy-illuminating-piano,news-20887.html | Not opened (snippet) |
| https://apps.apple.com/us/app/led-piano/id6444875266 | Yes |
| https://ask.metafilter.com/195093/Do-light-up-keyboards-help-learning-piano | Not opened (snippet) |
| https://www.reddit.com/r/piano/search/?q=piano+led+strip&restrict_sr=1 | No (fetch tool blocked from reddit.com) |

---

## 4. Could not verify

- **Prices:**
  - Piano LED Plus in USD (the site shows EUR only).
  - Current price and availability of the Hi-Lite. Amazon returned 503, the official product page is gone, and it may be discontinued.
  - Current ROLI Piano and LUMI prices.
  - i-Piano price on a live page (Etsy and eBay returned 403).
  - Pianissimo reward price.
- **Amazon star ratings and reviews** for any product. Amazon blocked fetching.
- **Reddit:** No threads could be read, because the fetch tool is blocked and site: searches returned nothing. Reddit complaints are therefore missing. Recommend a manual read of r/piano and r/synthesia.
- **Mounting details:**
  - The type of KEEZI's mounting kit.
  - i-Piano and PianoMaestro mounting.
- **Hi-Lite detection:** Whether it really uses laser detection (only one source, Gizmodo JP, says so).
- **Patent 11,087,636:** Assignee, claims and status.
- **Generic Kmise/Amazon/AliExpress "piano LED strip" products:** None found. They may exist under names I didn't hit.
- **Unnamed hardware for the Vietnamese "LED Piano" app:** Name unverified.
- **PianoMaestro:** Maker, price and current status (no primary source found).
- **Pianissimo:** Whether it reads key presses, and its Kickstarter totals (Kicktraq was down).
- **KEEZI:** Company location.
