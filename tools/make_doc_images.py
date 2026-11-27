"""Draw the documentation figures that depend on real numbers, from the code itself.

    python tools/make_doc_images.py

Writes docs/images/led-strip.svg (which LEDs light for which key, from plans.led_span)
and docs/images/rig-layout.svg (bottle positions along the rail, from the profile).
Re-run after changing a profile so the pictures stay true.
"""

from __future__ import annotations

from pathlib import Path

from duet.pitch import is_black_key, midi_to_name
from duet.plans import led_span
from duet.profile import keyboard_profile, robot_profile

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def led_strip(low: int = 60, high: int = 72) -> str:
    kb = keyboard_profile()
    spans = {m: led_span(m, kb) for m in range(low, high + 1)}
    first_led = min(f for f, _ in spans.values()) - 2
    last_led = max(f + c for f, c in spans.values()) + 1
    led_w = 1000 / kb.led.leds_per_m  # mm per LED
    scale = 7.0  # px per mm
    left = 60
    width = int(left * 2 + (last_led - first_led) * led_w * scale)
    whites = [m for m in range(low, high + 1) if not is_black_key(m)]
    white_w = kb.led.white_key_mm * scale
    origin_mm = (first_led) * led_w  # strip mm at the left edge of the drawing
    whites_before = sum(1 for m in range(kb.low, low) if not is_black_key(m))

    def key_x(mm: float) -> float:
        return left + (mm - origin_mm) * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 380" {FONT} font-size="13">',
        "<title>Which LEDs light above each key, one octave from C4 to C5</title>",
        f'<rect width="{width}" height="380" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="26" text-anchor="middle" font-size="17" font-weight="bold" '
        f'fill="#222">LED strip over the keys: C4 to C5 (144 LEDs per metre)</text>',
    ]
    # LEDs
    for i in range(first_led, last_led):
        x = key_x(i * led_w)
        lit = next((m for m, (f, c) in spans.items() if f <= i < f + c), None)
        fill = (
            "#facc15"
            if lit is not None and not is_black_key(lit)
            else "#a78bfa"
            if lit
            else "#e5e7eb"
        )
        parts.append(
            f'<rect x="{x + 1:.1f}" y="60" width="{led_w * scale - 2:.1f}" height="16" rx="3" '
            f'fill="{fill}" stroke="#9ca3af" stroke-width="0.5"/>'
        )
        if i % 5 == 0:
            parts.append(
                f'<text x="{x + led_w * scale / 2:.1f}" y="52" text-anchor="middle" fill="#666" font-size="10">{i}</text>'
            )
    parts.append(
        f'<text x="{left - 8}" y="73" text-anchor="end" fill="#222" font-size="12">LEDs</text>'
    )
    # keys
    for n, m in enumerate(whites):
        x = key_x((whites_before + n) * kb.led.white_key_mm)
        parts.append(
            f'<rect x="{x:.1f}" y="110" width="{white_w:.1f}" height="200" fill="#ffffff" stroke="#111"/>'
        )
        parts.append(
            f'<text x="{x + white_w / 2:.1f}" y="300" text-anchor="middle" fill="#111" font-weight="bold">{midi_to_name(m)}</text>'
        )
    for m in range(low, high + 1):
        if is_black_key(m):
            below = whites_before + sum(1 for k in range(low, m) if not is_black_key(k))
            cx = key_x(below * kb.led.white_key_mm)
            bw = white_w * 0.58
            parts.append(
                f'<rect x="{cx - bw / 2:.1f}" y="110" width="{bw:.1f}" height="125" fill="#111"/>'
            )
            parts.append(
                f'<text x="{cx:.1f}" y="228" text-anchor="middle" fill="#fff" font-size="10">{midi_to_name(m)}</text>'
            )
    # light beams from LED spans to key centres
    for m, (f, c) in spans.items():
        x0 = key_x(f * led_w)
        x1 = key_x((f + c) * led_w)
        colour = "#a78bfa" if is_black_key(m) else "#eab308"
        parts.append(
            f'<path d="M{x0:.1f},78 L{x1:.1f},78 L{(x0 + x1) / 2 + 3:.1f},{105 if is_black_key(m) else 120} '
            f'L{(x0 + x1) / 2 - 3:.1f},{105 if is_black_key(m) else 120} z" fill="{colour}" opacity="0.35"/>'
        )
    parts.append(
        f'<text x="{width / 2}" y="340" text-anchor="middle" fill="#444">'
        f"Each key lights the ~2 LEDs centred over it (1/12 of an octave). "
        f"C4 = LEDs {spans[low][0]}–{spans[low][0] + spans[low][1] - 1}, "
        f"E4 = {spans[64][0]}–{spans[64][0] + spans[64][1] - 1}, "
        f"C5 = {spans[high][0]}–{spans[high][0] + spans[high][1] - 1}.</text>"
    )
    parts.append(
        f'<text x="{width / 2}" y="362" text-anchor="middle" fill="#666" font-size="12">'
        f"White key {kb.led.white_key_mm} mm · LED pitch {led_w:.2f} mm · "
        f"yellow: white keys · violet: black keys · from plans.led_span()</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def rig_layout() -> str:
    robot = robot_profile()
    kin = robot.kinematics
    travel_mm = kin.travel_steps / kin.steps_per_mm
    scale = 1.25  # px per mm
    left, right_pad = 130, 190
    width = int(left + travel_mm * scale + right_pad)

    def x(mm: float) -> float:
        return left + mm * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 470" {FONT} font-size="13">',
        "<title>Rig front view: bottles hanging from the gantry, carriage and striker below</title>",
        f'<rect width="{width}" height="470" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="26" text-anchor="middle" font-size="17" font-weight="bold" fill="#222">'
        f"Rig, front view ({robot.id})</text>",
        # gantry
        f'<rect x="{x(-60)}" y="50" width="{travel_mm * scale + 150}" height="12" fill="#9ca3af"/>',
        f'<text x="{x(-60)}" y="44" fill="#444" font-size="12">gantry top bar (aluminium tube)</text>',
        f'<rect x="{x(-60)}" y="50" width="10" height="330" fill="#9ca3af"/>',
        f'<rect x="{x(travel_mm) + 80}" y="50" width="10" height="330" fill="#9ca3af"/>',
    ]
    for b in robot.notes:
        cx = x(b.steps / kin.steps_per_mm)
        parts += [
            f'<line x1="{cx}" y1="62" x2="{cx}" y2="80" stroke="#444" stroke-width="2"/>',
            f'<rect x="{cx - 6}" y="78" width="12" height="10" rx="2" fill="#111"/>',  # rubber cap
            f'<path d="M{cx - 5},88 L{cx - 5},110 Q{cx - 22},122 {cx - 22},150 L{cx - 22},225 '
            f"Q{cx - 22},235 {cx - 12},235 L{cx + 12},235 Q{cx + 22},235 {cx + 22},225 L{cx + 22},150 "
            f'Q{cx + 22},122 {cx + 5},110 L{cx + 5},88 z" fill="#bfdbfe" stroke="#1d4ed8" stroke-width="1.5"/>',
            f'<text x="{cx}" y="180" text-anchor="middle" fill="#1e3a8a" font-weight="bold">{midi_to_name(b.midi)}</text>',
            f'<line x1="{cx}" y1="240" x2="{cx}" y2="252" stroke="#94a3b8" stroke-dasharray="2 2"/>',
            f'<text x="{cx}" y="414" text-anchor="middle" fill="#444" font-size="11">{b.steps / kin.steps_per_mm:.0f} mm</text>',
            f'<text x="{cx}" y="428" text-anchor="middle" fill="#888" font-size="10">{b.steps} st</text>',
        ]
    last = x(robot.notes[-1].steps / kin.steps_per_mm)
    parts.append(f'<line x1="{last + 8}" y1="83" x2="{last + 40}" y2="83" stroke="#444"/>')
    parts.append(f'<text x="{last + 44}" y="87" fill="#444" font-size="11">rubber neck caps</text>')
    # rails and belt
    parts += [
        f'<line x1="{x(-40)}" y1="330" x2="{x(travel_mm) + 70}" y2="330" stroke="#6b7280" stroke-width="5"/>',
        f'<line x1="{x(-40)}" y1="345" x2="{x(travel_mm) + 70}" y2="345" stroke="#6b7280" stroke-width="5"/>',
        f'<text x="{x(travel_mm) + 75}" y="341" fill="#444" font-size="11">2 steel rods</text>',
        f'<line x1="{x(-30)}" y1="362" x2="{x(travel_mm) + 60}" y2="362" stroke="#111" stroke-width="2" stroke-dasharray="6 3"/>',
        f'<text x="{x(travel_mm / 2)}" y="380" text-anchor="middle" fill="#444" font-size="11">GT2 timing belt</text>',
    ]
    # carriage at G5 with striker
    g5 = next(b for b in robot.notes if midi_to_name(b.midi) == "G5")
    cx = x(g5.steps / kin.steps_per_mm)
    parts += [
        f'<rect x="{cx - 26}" y="300" width="52" height="54" rx="4" fill="#fde68a" stroke="#b45309"/>',
        f'<rect x="{cx - 9}" y="285" width="18" height="22" fill="#f59e0b" stroke="#b45309"/>',
        f'<line x1="{cx}" y1="285" x2="{cx}" y2="255" stroke="#b45309" stroke-width="4"/>',
        f'<text x="{cx + 32}" y="272" fill="#92400e" font-size="12">striker rod</text>',
        f'<text x="{cx + 32}" y="300" fill="#92400e" font-size="12">solenoid on the carriage</text>',
    ]
    # motor end and idler
    parts += [
        f'<rect x="{x(-58)}" y="330" width="44" height="44" fill="#374151"/>',
        f'<text x="{x(-36)}" y="350" text-anchor="middle" fill="#fff" font-size="9">NEMA</text>',
        f'<text x="{x(-36)}" y="361" text-anchor="middle" fill="#fff" font-size="9">17</text>',
        f'<circle cx="{x(-28)}" cy="362" r="7" fill="#9ca3af"/>',
        f'<rect x="{x(-8)}" y="300" width="14" height="22" rx="3" fill="#10b981"/>',
        f'<text x="{x(-1)}" y="292" text-anchor="middle" fill="#047857" font-size="11">home sensor</text>',
        f'<circle cx="{x(travel_mm) + 58}" cy="362" r="7" fill="#9ca3af"/>',
        f'<text x="{x(travel_mm) + 58}" y="392" text-anchor="middle" fill="#444" font-size="11">idler</text>',
        f'<text x="{x(-36)}" y="392" text-anchor="middle" fill="#444" font-size="11">motor end</text>',
        f'<line x1="{x(0)}" y1="440" x2="{x(travel_mm)}" y2="440" stroke="#444"/>',
        f'<text x="{x(0)}" y="458" fill="#444" font-size="11">0 = home</text>',
        f'<text x="{x(travel_mm)}" y="458" text-anchor="end" fill="#444" font-size="11">'
        f"travel limit {travel_mm:.0f} mm ({kin.travel_steps} steps)</text>",
    ]
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "led-strip.svg").write_text(led_strip(), encoding="utf-8")
    (OUT / "rig-layout.svg").write_text(rig_layout(), encoding="utf-8")
    print(f"wrote {OUT / 'led-strip.svg'} and {OUT / 'rig-layout.svg'}")


if __name__ == "__main__":
    main()
