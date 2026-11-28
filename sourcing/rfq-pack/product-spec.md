# DK-1 product specification (for quotation)

**Working name:** DUET KEYS DK-1. The name is a placeholder until a trademark search is done.
**What it is:** an LED rail that lies behind the keys of any 88-key piano, acoustic or digital, and lights the next key to play. An ESP32 runs its own Wi-Fi network and web page, where the user uploads a MIDI file. It needs no app and no MIDI cable.

## Finished product

| | |
|---|---|
| Lit length | 1,222 mm: 176 LEDs, 2 per key |
| Rail | 2 halves × 625 mm black anodised aluminum profile (17.6 × 15.8 mm), black diffuser, joined by a printed joiner |
| Controller end | Printed nylon cap about 73 × 42 × 25 mm holding the controller board; USB-C port on the outer end |
| Far end | Printed blank end cap |
| Support | Felt-padded joiner and 2 feet; **no adhesive on the piano** |
| Power | USB-C, 5 V, up to 3 A, from the user's phone charger (no adapter in the box) |
| Radio | 2.4 GHz Wi-Fi from a pre-certified ESP32 module (module FCC ID to be confirmed by the controller supplier) |
| Microphone | On-board ICS-43434 I2S MEMS mic, for note detection (firmware feature) |
| Firmware | Supplied by the customer as one merged binary; flashed and tested at the factory (`factory/`) |
| Packaging | Printed corrugated box, inside 26 × 4 × 3 in, with insert, quick-start card, manual and UPC label |
| Market | USA. FCC Part 15 Class B (customer arranges the test); "Made in China" marking |

## Documents in this pack

| File | Contents |
|---|---|
| `bom.csv` | 16-line bill of materials with preferred sources and alternates |
| `cad/out/*.step`, `*.stl` | Printed parts DK1-01 to DK1-05, plus a controller-end assembly |
| `cad/parts.py` | Parametric source; `VERIFY` notes mark dimensions to check against samples |
| `wiring.svg` | Wiring diagram |
| `factory/factory-instructions.md` | Incoming inspection, assembly, flashing and test, packing |
| `factory/flash_and_test.py` | Test-station script; writes the per-unit test log |
| `print/` | Manual, quick-start card, labels and box artwork |

## Quantities to quote

100 units (pilot), 500 units and 1,000 units, plus **3–5 pre-production samples**.

## What we ask the factory to quote

1. **Turnkey price per unit at each quantity.** Show these separately:
   - each BOM line;
   - printing;
   - assembly labour;
   - flashing and test;
   - packaging;
   - packing.
2. **One-off costs:** fixtures, test jig, print plates, moulds if proposed.
3. **Samples:** cost and lead time.
4. **Production:** lead time.
5. **Prices on two bases:**
   - **EXW / FOB Shenzhen**;
   - **DDP** to a US address (ZIP to be supplied).
6. **Packed unit:** weight and carton size, and units per master carton.
7. **Documents we will need from you:**
   - FCC grant of the ESP32 module used;
   - any FCC Part 15B / SDoC, CE or RoHS reports for the controller;
   - a lead and phthalate (RoHS) test of the strip and cable.
