"""Single source of the printed wording. Change BRAND etc. here; run build_all.py."""
BRAND = "DUET KEYS"          # PLACEHOLDER — trademark search needed before printing
MODEL = "DK-1"
TAGLINE = "LED piano learning light for any piano — acoustic or digital. No app, no MIDI cable."
SSID = "DUET-KEYS-xxxx"
FCC_ID = "[MODULE FCC ID — confirm from controller supplier]"
PARTY = "[Company name], [Street], [City, State ZIP], USA, [email / website]"
MANUAL_URL = "[online manual URL]"
WARRANTY = "[1-year limited warranty — CONFIRM terms]"
POWER = "5 V DC, 3 A"   # the IEC 60417-5031 DC symbol (⎓) can replace "DC" in final artwork

FCC_1519 = ("This device complies with part 15 of the FCC Rules. Operation is subject to the "
            "following two conditions: (1) This device may not cause harmful interference, and "
            "(2) this device must accept any interference received, including interference that "
            "may cause undesired operation.")
FCC_1521 = ("Caution: Changes or modifications not expressly approved by the party responsible "
            "for compliance could void the user's authority to operate the equipment.")
FCC_15105 = ("Note: This equipment has been tested and found to comply with the limits for a "
             "Class B digital device, pursuant to part 15 of the FCC Rules. These limits are "
             "designed to provide reasonable protection against harmful interference in a "
             "residential installation. This equipment generates, uses and can radiate radio "
             "frequency energy and, if not installed and used in accordance with the instructions, "
             "may cause harmful interference to radio communications. However, there is no "
             "guarantee that interference will not occur in a particular installation. If this "
             "equipment does cause harmful interference to radio or television reception, which "
             "can be determined by turning the equipment off and on, the user is encouraged to try "
             "to correct the interference by one or more of the following measures:")
FCC_15105_BULLETS = [
    "Reorient or relocate the receiving antenna.",
    "Increase the separation between the equipment and receiver.",
    "Connect the equipment into an outlet on a circuit different from that to which the receiver is connected.",
    "Consult the dealer or an experienced radio/TV technician for help.",
]
RF_EXPOSURE = ("This equipment should be installed and operated with a minimum distance of 20 cm "
               "between the antenna and your body. [CONFIRM WITH TEST LAB — placeholder; the module "
               "grant's 20 cm condition is under review for this use]")

CONTENTS = [
    "2 × rail halves (625 mm each, black aluminum with black diffuser; 176 LEDs in total, 88 per half)",
    "1 × controller end cap (USB-C port)",
    "1 × blank end cap",
    "1 × joiner",
    "2 × felt support feet",
    "1 × USB-C cable, 1 m",
]
ADAPTER_NOTE = ("Power adapter not included. Use a USB-C or USB-A phone charger, 5 V, 3 A (15 W) "
                "recommended; use a UL/ETL-listed adapter.")

# Manual: list of (heading, [blocks]); block = ("p", text) | ("ul", [..]) | ("ol", [..]) | ("table", [[..],..]) | ("note", text)
MANUAL = [
 ("Welcome", [
   ("p", f"{BRAND} {MODEL} is an LED rail that sits behind the keys of your piano and lights the next key to play. "
         "It works on acoustic and digital pianos. You do not need an app, a computer or a MIDI cable: "
         "the rail makes its own Wi-Fi network and you use it from your phone's web browser."),
 ]),
 ("What's in the box", [("ul", CONTENTS), ("note", ADAPTER_NOTE)]),
 ("Safety", [("ul", [
   "Indoor, dry use only. Keep away from drinks, vases and humidifiers.",
   "Do not cover the rail while it is on.",
   "Do not stare into the LEDs at full brightness from close up.",
   "Route the cable away from the piano action, the pedals and walkways.",
   "This is not a toy. Not for children under 14 without supervision. [CONFIRM WITH ATTORNEY — children's product decision pending]",
   "Unplug the cable before cleaning or moving the rail.",
 ])]),
 ("1. Assemble the rail", [("ol", [
   "Lay both rail halves end to end on a soft surface, LEDs facing up.",
   "Push the joiner into the inner ends of both halves until the halves meet. The strip connector inside the joiner clicks together.",
   "Fit the controller end cap on the left end (bass end) and the blank end cap on the right end.",
   "Clip the two felt feet under the rail, about a quarter of the way in from each end.",
 ])]),
 ("2. Place it on your piano", [
   ("p", "Lay the rail on the flat strip just behind the keys, in front of the fallboard, standing on its felt feet. "
         "Nothing sticks to your piano: no adhesive, no screws."),
   ("ul", [
     "Line up the arrow mark on the rail with middle C (C4).",
     "Make sure the fallboard (key cover) can still close without touching the rail; if not, remove the rail before closing it.",
     "On pianos with a narrow ledge, let the rail rest on the felt feet only; it must not touch the keys.",
   ]),
 ]),
 ("3. Power it on", [
   ("p", f"Plug the USB-C cable into the controller end cap and into a phone charger. The LEDs run a short start-up pattern. "
         f"A 5 V, 3 A (15 W) charger gives full brightness. A weaker charger or a computer USB port works, but {BRAND} "
         "automatically lowers the brightness to stay within what the charger can supply."),
 ]),
 ("4. Connect your phone", [("ol", [
   f"On your phone or tablet, open Wi-Fi settings and join the network {SSID} (the last four characters differ on each unit).",
   "The control page should open by itself. If it does not, open your web browser and go to http://192.168.4.1",
   "Your phone may warn that this network has no internet. That is normal; stay connected.",
 ]), ("note", "Home Wi-Fi mode (planned): a future update lets the rail join your home network so you can stay on your own Wi-Fi.")]),
 ("5. Calibrate the keys", [
   ("p", "Every piano is slightly different. Calibration matches the lights to your keys."),
   ("ol", [
     "On the control page, open Settings → Calibrate.",
     "Tap the lowest and highest key you can see lit, then adjust the middle C marker until the light sits over middle C.",
     "Check a few keys across the keyboard and save.",
   ]),
 ]),
 ("6. Play a song", [("ol", [
   "On the control page, tap Upload and choose a MIDI file (.mid) from your phone.",
   "Choose which hand or track to show, and the speed.",
   "Press Start and play the lit keys. The next key to play lights up; right and left hand use different colors.",
 ])]),
 ("Brightness and power", [
   ("p", "176 LEDs at full white would need more power than a phone charger can give, so the brightness is limited in software. "
         "If the lights look dim or flicker, use a 5 V, 3 A charger and the supplied cable. Long or thin cables lower brightness too."),
 ]),
 ("Troubleshooting", [("table", [
   ["Problem", "What to try"],
   ["No lights at all", "Check both ends of the cable. Try another charger. Make sure the joiner is fully pushed in."],
   ["Right half dark", "The joiner is not fully seated. Unplug, push the halves together until they meet, plug back in."],
   [f"Cannot see {SSID}", "Wait 30 seconds after plugging in. Move the phone closer. Unplug and plug back in."],
   ["Page does not open", "Stay on the rail's network and browse to http://192.168.4.1. Turn off mobile data if your phone keeps switching away."],
   ["Lights do not line up with keys", "Run Settings → Calibrate again and check the arrow is at middle C."],
   ["Lights dim or flicker", "Use a 5 V, 3 A charger. Avoid USB hubs and laptop ports."],
   ["MIDI file will not load", "Use a standard .mid file under the size shown on the upload page."],
 ])]),
 ("Care", [("ul", [
   "Wipe with a soft, dry cloth. Do not use solvents or sprays on the diffuser or the piano.",
   "Store the rail flat or in its box. Do not bend the rail halves.",
   "To take the rail apart, pull the halves straight out of the joiner; do not twist.",
 ])]),
 ("Specifications", [("table", [
   ["Item", "Value"],
   ["Model", MODEL],
   ["Power input", f"{POWER} max, USB-C"],
   ["LEDs", "176 addressable RGB LEDs (WS2812B type), 144 per metre, 2 per key (88 keys)"],
   ["Wireless", "Wi-Fi 2.4 GHz, 802.11 b/g/n"],
   ["Length", "Lit length 1,222 mm; 2 × 625 mm rail halves plus end caps, approx. 1.3 m overall [CONFIRM from final CAD]"],
   ["Controller end cap", "Approx. 73 × 42 × 25 mm"],
   ["Rail section", "Approx. 17.6 × 15.8 mm [CONFIRM from final CAD]"],
   ["Weight", "[CONFIRM after weighing a production sample]"],
   ["Use", "Indoor, dry locations, 0–40 °C [CONFIRM]"],
 ])]),
 ("Warranty", [("p", f"{WARRANTY}. Contact: {PARTY}. Online manual: {MANUAL_URL}")]),
 ("FCC information", [
   ("p", FCC_1519), ("p", FCC_1521), ("p", FCC_15105), ("ul", FCC_15105_BULLETS),
   ("p", f"Contains FCC ID: {FCC_ID}"),
   ("p", RF_EXPOSURE),
 ]),
 ("Supplier's Declaration of Conformity — compliance information", [("p", "Made in China."), ("table", [
   ["Item", "Value"],
   ["Product name", f"{BRAND} LED piano learning light"],
   ["Model", MODEL],
   ["Statement", FCC_1519],
   ["Contains module", f"FCC ID: {FCC_ID}"],
   ["US responsible party", PARTY],
 ])]),
]
