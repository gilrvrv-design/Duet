# DK-1 factory instructions: assembly, flashing, test, packing

These instructions are for the contract manufacturer. Part numbers refer to `../bom.csv`. Part files are in `../cad/out/` and the wiring is in `../wiring.svg`.

## 1. Incoming inspection (sample 5 per lot)

- **LED strip (DK1-10):** connect 1 m to a 5 V bench supply set to 1.5 A, with a simple test pattern. Check for dead LEDs and wrong colours. Measure the width with calipers: it must fit the 12.2 mm profile channel.
- **Profile (DK1-11):** length 625.0 ± 0.5 mm, ends square and deburred, no scratches on the top face, diffuser clips in fully.
- **Controller (DK1-20):** powers up from USB-C, and the USB-C port is not loose.
- **Printed parts (DK1-01 to 05):** black, no warping. A profile offcut slides into both end caps with light hand force, and the joiner and feet grip the profile.

## 2. Assembly (per unit)

1. **Strip halves.** Cut two strips of exactly **88 LEDs**, on the printed cut lines.
   - **Half A:** solder pigtail DK1-30 to the DIN end (5V / DATA / GND) and the male half of DK1-31 to the DOUT end.
   - **Half B:** solder the female half of DK1-31 to its DIN end. Insulate the far end with heat-shrink.
2. **Fit the strips into the profiles.** Peel the tape and press each strip into a profile, centred along its length, so 7 mm of profile is empty at each end. The data arrows must point away from the controller end. Snap in the black diffuser.
3. **Controller.** Remove the Dig2Go from its own case if it was supplied in one. Fix it on the three standoffs in cap base DK1-01 with 3 × M2 × 6 screws, USB-C facing the opening.
4. **Connect.** Feed pigtail DK1-30 through the wire slot into the sleeve, and plug it into the Dig2Go LED output. Slide rail half A into the sleeve until it stops.
5. **Close.** Fit lid DK1-02 with 4 × M2 × 6 screws. Do not over-tighten: the parts are nylon.
6. **Feet.** Stick the felt pads into every recess on the bottoms of the parts.
7. **Label.** Stick the rating label DK1-50 on the controller cap, and the serial label on the cap underside.

## 3. Flashing and test (every unit, 100%)

Station: a Windows or Linux PC, `pip install esptool pyserial`, `flash_and_test.py`, and the firmware image `dk1-firmware-merged.bin` (supplied by the customer for each release, with a version number and checksum).

1. Temporarily join the two rail halves with the joiner, so the unit runs as one 176-LED strip.
2. Plug the unit into the PC with the USB-C cable.
3. Run `python flash_and_test.py --port <port> --serial DK1-xxxxxx`.
4. The script flashes the firmware, resets the board and reads the self-test line.
5. Watch the LED sweep: red, green, blue, then white, across all 176 LEDs.
   - Any dead LED, wrong colour, or a strip that stops partway is a **FAIL**.
6. Check the unit's Wi-Fi network `DUET-KEYS-xxxx` is visible on the test phone.
7. Clap once near the controller cap. The self-test output shows the microphone level rising. A level of 0 is a **FAIL**.
8. Only **PASS** units go to packing.
9. Return `dk1_test_log.csv` with every shipment.

Target time: under 2 minutes per unit, of which flashing is about 30–40 s.

## 4. What the firmware must provide (customer action)

- One serial line at 115200 baud on boot:
  `SELFTEST {"result","fw","mac","leds","mic_rms","ssid"}` (see the script header).
- A boot pattern of red, green, blue and white sweeps at 20% brightness, then a rainbow.
- An SSID made from the MAC address (`DUET-KEYS-` plus the last 4 hex digits).
- A merged single image at offset 0x0, built with `esptool merge_bin`.
- A brightness and current cap of 2.5 A for the LEDs. Reduce it further when the USB-C CC line advertises less than 3 A.

## 5. Packing (per box)

1. Separate the rail halves and put each in a poly sleeve. Lay them in insert DK1-61, side by side and not touching.
2. In the parts pocket:
   - controller cap with rail half A attached, if the insert allows; otherwise detached
   - blank end cap
   - joiner
   - 2 feet
   - USB-C cable, coiled with a twist tie
3. Lay the quick-start card on top and the manual under it.
4. Close the box and apply box label DK1-62 with the UPC.
5. Pack master cartons of 10 boxes. Mark them "Made in China", with carton number, quantity and gross weight.

## 6. Quality records to keep and send

- Test log CSV per lot.
- Firmware version and checksum used.
- Lot numbers of the LED strip and controller.
- Photos of 1 packed unit per lot.
