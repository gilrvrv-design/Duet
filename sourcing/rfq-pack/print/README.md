# Printed material: DK-1

Every file here is generated from `src/content.py`, so the wording only lives in one place. To change the brand, company, FCC ID or any text, edit `content.py` and run:

```bash
python src/build_all.py
```

This needs `reportlab` and `svglib` (`pip install reportlab svglib`).

| File | What it is | Print spec |
|---|---|---|
| `manual.md` / `manual.pdf` | User manual, 7 pages at 5.5 × 8.5 in. Covers: what's in the box, safety, assembly, placement, power, connecting, calibration, play, brightness, troubleshooting, care, specs, warranty, full FCC statements (15.19, 15.21, 15.105(b)), and the 2.1077 compliance information statement | Text weight 80–100 gsm, saddle-stitched. A 4-page cover plus 4-page insert also works. The FCC page can be printed as a separate sheet |
| `quickstart.pdf` | Quick-start card, 6 × 4 in, two sides: 4 illustrated steps, help tips, QR placeholder, short FCC line | 300–350 gsm card, matte |
| `labels.pdf` | A: rating label for the controller end cap, 30 × 15 mm at actual size, plus a 4× proof. B: box information label, 4 × 2 in, with a UPC area | PET (polyester) label, permanent adhesive; type no smaller than 3.6 pt |
| `box-artwork.svg` / `box-artwork.pdf` | Flat dieline plus artwork for an end-loading RSC (regular slotted carton), inside 660.4 × 101.6 × 76.2 mm (26 × 4 × 3 in). Red solid lines are cuts, blue dashed are folds, with 1/8 in (3.175 mm) bleed. Panels: TOP (brand and keys), FRONT (brand and tagline), BACK (features), BOTTOM (contents, compliance, Made in China, barcode); end flaps carry the brand | White E- or B-flute corrugated, full colour outside. **The printer's own dieline template governs the final dimensions**: re-place this artwork on Packlane's (or your printer's) template for 26 × 4 × 3 in |

## Placeholders to replace before printing

| Placeholder | Where it appears | Replace with |
|---|---|---|
| `DUET KEYS` (brand) | Everything (`BRAND` in content.py) | Your brand, **after a USPTO trademark search**. Amazon Brand Registry needs a filed or registered mark |
| `[Company name], [Street], …` | Manual, labels, box, card | Your US company: the FCC SDoC responsible party must be in the US (47 CFR 2.1077) |
| `[MODULE FCC ID …]` / `[MODULE ID]` | Rating label, box, manual, card | The FCC ID of the Wi-Fi module on the controller you choose. Get it from the supplier and check it on the FCC ID database |
| UPC-A box | Box bottom panel, box label | A GTIN or UPC bought from GS1 US. Add an FNSKU label if you sell through FBA |
| `[1-year limited warranty — CONFIRM terms]` | Manual | Your warranty terms |
| `[online manual URL]` / QR box | Card, manual | Your support page URL and a QR code |
| `[CONFIRM WITH TEST LAB]` RF exposure line | Manual | The test lab's wording, or delete it. The module grant's 20 cm condition still needs checking for this use |
| `[CONFIRM WITH ATTORNEY]` age line | Manual | The final wording once you decide whether to market to children |
| `[CONFIRM from final CAD]`, weight, temperature range | Manual specs | Measured values from production samples |
| `SN: DK1-XXXXXX` | Rating label | Sequential serials, printed by the assembly partner |

## Notes

- The power rating is written "5 V DC, 3 A" because the build font lacks the ⎓ symbol (IEC 60417-5031). A designer can swap it in for the final artwork.
- The manual describes features the firmware still has to provide: the captive portal, home Wi-Fi mode, the Settings → Calibrate page, and the left/right-hand colours. Change the wording if the firmware differs.
- The LED count is 176 (88 keys × 2, as two strips of 88). The lit length is 1,222 mm, and the controller end cap is about 73 × 42 × 25 mm (from the CAD).
