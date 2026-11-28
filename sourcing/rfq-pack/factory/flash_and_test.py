#!/usr/bin/env python3
"""DK-1 factory station: flash one controller, run its self-test, log the result.

Setup (once):   pip install esptool pyserial
Per unit:       python flash_and_test.py --port COM5            (Windows)
                python flash_and_test.py --port /dev/ttyUSB0     (Linux/macOS)

The operator plugs the assembled unit (controller + both strip halves) into the PC by USB-C,
runs this script, watches the LED pattern, answers y/n, and sticks the printed serial label on.
Results are appended to dk1_test_log.csv - send that file back with every shipment.

Firmware contract (implemented by the customer's firmware, see factory-instructions.md section 4):
on boot it prints one line:
  SELFTEST {"result":"PASS","fw":"1.0.0","mac":"AA:BB:CC:DD:EE:FF","leds":176,"mic_rms":123,"ssid":"DUET-KEYS-EEFF"}
and shows red -> green -> blue -> white (20 %) sweeps across all 176 LEDs, then a slow rainbow.
"""
import argparse, csv, datetime, json, os, subprocess, sys, time

FIRMWARE = "dk1-firmware-merged.bin"   # single merged image written at offset 0x0
BAUD_FLASH = 921600
BAUD_LOG = 115200
LOG = "dk1_test_log.csv"

def flash(port, image):
    cmd = [sys.executable, "-m", "esptool", "--chip", "esp32", "--port", port, "--baud", str(BAUD_FLASH),
           "write_flash", "--flash_mode", "dio", "--flash_size", "detect", "0x0", image]
    print(">", " ".join(cmd))
    return subprocess.run(cmd).returncode == 0

def read_selftest(port, timeout=20):
    import serial
    with serial.Serial(port, BAUD_LOG, timeout=1) as s:
        s.dtr = False; s.rts = True; time.sleep(0.1); s.rts = False   # reset into the app
        end = time.time() + timeout
        while time.time() < end:
            line = s.readline().decode(errors="replace").strip()
            if line:
                print("  |", line)
            if line.startswith("SELFTEST "):
                return json.loads(line[len("SELFTEST "):])
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--image", default=FIRMWARE)
    ap.add_argument("--serial", help="serial number printed on the label, e.g. DK1-000123")
    ap.add_argument("--skip-flash", action="store_true")
    a = ap.parse_args()
    sn = a.serial or input("Serial number on label: ").strip()
    ok_flash = True if a.skip_flash else flash(a.port, a.image)
    st = read_selftest(a.port) if ok_flash else None
    ok_self = bool(st) and st.get("result") == "PASS" and st.get("leds") == 176
    seen = input("Did ALL 176 LEDs show red, green, blue and white with no dead or wrong-colour LED? [y/n] ").strip().lower() == "y"
    wifi = input(f"Is Wi-Fi network {st.get('ssid') if st else '?'} visible on the test phone? [y/n] ").strip().lower() == "y"
    passed = ok_flash and ok_self and seen and wifi
    row = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "serial": sn,
           "flash_ok": ok_flash, "selftest": json.dumps(st) if st else "", "leds_visual_ok": seen,
           "wifi_ok": wifi, "result": "PASS" if passed else "FAIL"}
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
    print("\n" + ("PASS - pack it" if passed else "FAIL - put it in the red bin, do not pack"))
    sys.exit(0 if passed else 1)

if __name__ == "__main__":
    main()
