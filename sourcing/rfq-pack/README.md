# DK-1 manufacturing pack: everything a factory needs to quote and build it

**Attach `rfq-pack.zip`, one folder up, to the emails in `emails/`.**

| Folder or file | What it is |
|---|---|
| `product-spec.md` | One-page product description and the quote request |
| `bom.csv` | 16-line bill of materials with sources and alternates |
| `cad/` | 5 printed parts as STEP and STL, source `parts.py`, and a list of dimensions to verify |
| `wiring.svg` | Wiring diagram: controller → strip A → joint → strip B |
| `factory/` | Assembly, flashing, test and packing instructions, plus the test-station script |
| `print/` | Manual, quick-start card, labels and box artwork, as PDF and SVG, with the source that builds them |
| `emails/` | Four ready-to-send quote requests: Seeed Fusion, PCBWay, Elecrow, and an Alibaba LED factory |

## What only you can do

These need your name, your money or your hands. Everything else is drafted.

1. **Fill in your details.** Replace the placeholders: brand, company name and US address, warranty, manual URL. They are listed in `print/README.md`. Change `BRAND` and the company fields in `print/src/content.py`, then run `python print/src/build_all.py` to rebuild every PDF.
2. **Send the four emails** in `emails/` with `rfq-pack.zip` attached.
3. **Order the prototype parts and print the caps.** The list is in the chat. Upload `cad/out/*.stl` to JLC3DP, choosing MJF PA12 in black.
4. **Fit-check the samples** against the VERIFY table in `cad/README.md`, and tell me what's off. I'll adjust `parts.py`.
5. **Add the factory self-test to the firmware.** It is the `SELFTEST` line and boot pattern in `factory/factory-instructions.md` section 4. I can write this if you want.
6. **Book the regulated steps:**
   - FCC Part 15B test lab;
   - trademark filing;
   - GS1 US barcode;
   - customs broker for the HTS code and binding ruling.

## Known gaps

- The FCC ID of the module inside the Dig2Go is not published. Ask QuinLED, or read it off the module shield.
- The manual describes firmware features that don't exist yet: captive portal, home Wi-Fi mode, calibration page, colours for each hand.
- Board stack height, hole size, USB-C height and the LED header type all need checking on a real board.
