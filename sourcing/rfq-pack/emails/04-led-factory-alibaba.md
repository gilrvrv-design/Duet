# Quote request: LED strip / controller factory

Send via the supplier's Alibaba message box (e.g. Shenzhen Ledworker, GLEDOPTO, or an LED-kit factory found with an Alibaba search for 'WS2812B strip kit with controller OEM').
Subject: OEM inquiry: WS2812B strip + ESP32 controller + aluminum profile kit, custom firmware, private label

Attach: the whole `rfq-pack` folder as a zip (see ../README.md).

---

Hello Hello,

I'm launching a consumer LED product for the US market, the DUET KEYS DK-1: an LED rail that lies behind the keys of any piano and lights the next key to play. I'm looking for one partner to build it complete: source the parts, print the plastic parts, assemble, flash my firmware, test every unit and pack it in my printed box.

I've attached a complete pack:
- product-spec.md: what the product is and what I'd like quoted
- bom.csv: bill of materials, with my preferred part sources and alternates
- cad/out/: STEP and STL files for the five printed parts
- wiring.svg: wiring diagram
- factory/factory-instructions.md and flash_and_test.py: assembly, flashing, test and packing steps
- print/: manual, quick-start card, labels and box artwork

Could you please quote:
1. A turnkey price per unit at 100, 500 and 1,000 units, broken down by parts, printing, assembly, flashing and test, and packaging
2. Any one-off costs (fixtures, test jig, plates, moulds)
3. The cost and lead time for 3-5 pre-production samples
4. Your production lead time and minimum order
5. Prices EXW/FOB and DDP to the USA
6. The packed weight and carton size per unit
7. Which documents you can provide: the ESP32 module's FCC grant, any Part 15B/SDoC, CE or RoHS reports

Two questions before anything else, please:
- Can you flash MY firmware binary (not WLED) onto the controller and test it with my script?
- Can you supply the controller with an on-board I2S microphone and USB-C, or use the board in my BOM?
If you make strip, profile and controller in-house, please quote the full kit assembled and packed as described.

If you'd suggest any changes to make it cheaper to build (for example an injection-moulded end cap at 500+, or sourcing an equivalent controller board), I'd welcome them.

Thank you,

[Your name]
[Company] · [Website] · [Email] · [Phone]
