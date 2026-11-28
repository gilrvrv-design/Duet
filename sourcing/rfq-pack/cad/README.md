# DK-1 printed parts

`parts.py` is the parametric source. Run it with CadQuery 2.x (`pip install cadquery`, then `python parts.py`). It writes everything in `out/`:

| Part | File | Size (mm) | Volume |
|---|---|---|---|
| DK1-01 controller cap base, with sleeve onto the profile | `DK1-01_controller-cap-base.step/.stl` | 73.2 × 42.4 × 23.0 | 19.9 cm³ |
| DK1-02 controller cap lid (vents, mic port, 4 × M2) | `DK1-02_controller-cap-lid.step/.stl` | 59.2 × 42.4 × 4.0 | 5.0 cm³ |
| DK1-03 blank end cap | `DK1-03_blank-end-cap.step/.stl` | 16.2 × 22.6 × 20.6 | 3.3 cm³ |
| DK1-04 rail joiner | `DK1-04_rail-joiner.step/.stl` | 60.0 × 22.3 × 12.0 | 5.1 cm³ |
| DK1-05 support foot (×2 per unit) | `DK1-05_support-foot.step/.stl` | 25.0 × 22.3 × 12.0 | 2.2 cm³ |
| Controller end, assembled with a profile stub | `DK1-00_controller-end-assembly.step/.svg` | | |

A full set per unit is about **37.6 cm³, about 38 g** of PA12 nylon at its density of about 1.01 g/cm³, an assumed figure.

**Print settings:** HP MJF PA12, dyed black, at JLC3DP or similar. Resin (SLA) in black works for the first prototypes. Upload the STL files and print at the default tolerance.

## Design notes

- **Antenna clearance.** The controller sits in the plastic end cap. The ESP32 antenna edge faces the +Y side wall, away from the aluminum profile.
- **Mounting.** Every part holds the profile bottom 2.0 mm above the piano, on felt pads stuck into the recesses. There is no adhesive on the piano.
- **Fits.** The cap sleeves slide onto the profile with 0.30 mm clearance per side. The joiner and feet grip with 0.15 mm.
- **Diffuser kept clear.** The joiner and feet cover only the lower 10 mm of the profile sides, so no LED is hidden at the joint.

## VERIFY against physical samples before ordering

| Dimension | Value in `parts.py` | Where it came from |
|---|---|---|
| Profile outer section | 17.6 × 15.8 mm | SuperLightingLED page. Inner depth and wall thickness are not published |
| Dig2Go board outline and holes | 33.4 × 51.3 mm; 3 holes 2.6 mm from the edges | quinled.info dimension drawing, v1.05 |
| Board stack height and bottom-side parts | 17 mm total; 3 mm standoff | "about 17 mm" published; standoff is a guess |
| Mounting hole size | M2 self-tapping, 1.7 mm pilot | Not published |
| USB-C opening height | 13 × 9 mm centred on the board plane | USB-C side of the board not published |
| Mic port position | Read from the drawing pixels | Approximate |
| LED output header type and pin order | Not modelled | Not published |

**After the first print:** fit the parts to the real samples, then change the constants at the top of `parts.py` and re-export.
