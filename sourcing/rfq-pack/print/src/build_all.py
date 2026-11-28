"""Build every printed file from content.py:  python build_all.py
Needs reportlab + svglib. Outputs go one folder up (print/)."""
import os, sys, html
sys.path.insert(0, os.path.dirname(__file__))
from content import *
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                ListFlowable, ListItem, KeepTogether)
from reportlab.pdfgen import canvas

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FD = '/usr/share/fonts/truetype/dejavu/'
pdfmetrics.registerFont(TTFont('DV', FD + 'DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DVB', FD + 'DejaVuSans-Bold.ttf'))
from reportlab.lib.fonts import addMapping
addMapping('DV', 0, 0, 'DV'); addMapping('DV', 1, 0, 'DVB'); addMapping('DV', 0, 1, 'DV'); addMapping('DV', 1, 1, 'DVB')
ACCENT = colors.HexColor('#F2A900'); INK = colors.HexColor('#1A1A1A'); GREY = colors.HexColor('#6B6B6B')
esc = lambda s: html.escape(s, quote=False)

# ---------------------------------------------------------------- manual.md
def manual_md():
    L = [f"# {BRAND} {MODEL} — User manual", "", f"*{TAGLINE}*", ""]
    for head, blocks in MANUAL:
        if head: L += [f"## {head}", ""]
        for kind, val in blocks:
            if kind in ('p',): L += [val, ""]
            elif kind == 'note': L += [f"> {val}", ""]
            elif kind == 'ul': L += [f"- {v}" for v in val] + [""]
            elif kind == 'ol': L += [f"{i}. {v}" for i, v in enumerate(val, 1)] + [""]
            elif kind == 'table':
                L += ["| " + " | ".join(val[0]) + " |", "|" + "---|" * len(val[0])]
                L += ["| " + " | ".join(c.replace('|', '/') for c in r) + " |" for r in val[1:]] + [""]
    open(os.path.join(OUT, 'manual.md'), 'w').write("\n".join(L))

# ---------------------------------------------------------------- manual.pdf (5.5 x 8.5 in)
def manual_pdf():
    W, H = 5.5 * inch, 8.5 * inch
    st = lambda **k: ParagraphStyle('x', **{**dict(fontName='DV', fontSize=9, leading=12, textColor=INK), **k})
    body = st(spaceAfter=5); small = st(fontSize=7.2, leading=9.2, spaceAfter=4)
    h2 = ParagraphStyle('h2', fontName='DVB', fontSize=12, leading=15, spaceBefore=8, spaceAfter=5, textColor=INK)
    note = st(fontSize=8.5, leading=11, backColor=colors.HexColor('#FFF4D6'), borderPadding=5, spaceBefore=3, spaceAfter=8)
    story = []
    # cover
    story += [Spacer(1, 1.6 * inch), Paragraph(f'<font name="DVB" size="30">{esc(BRAND)}</font>', st(leading=36)),
              Spacer(1, 6), Paragraph(f'<font size="14">Model {MODEL} · User manual</font>', st(leading=18)),
              Spacer(1, 14), Paragraph(esc(TAGLINE), st(fontSize=11, leading=15, textColor=GREY)),
              Spacer(1, 2.4 * inch), Paragraph('Read the safety notes before use. Keep this manual.', st(textColor=GREY))]
    from reportlab.platypus import PageBreak
    story.append(PageBreak())
    fcc_small = False
    for head, blocks in MANUAL:
        sty = small if head.startswith(('FCC', "Supplier")) else body
        if head.startswith(('FCC', 'Supplier')): story.append(PageBreak())
        if head: story.append(Paragraph(esc(head), h2))
        for kind, val in blocks:
            if kind == 'p': story.append(Paragraph(esc(val), sty))
            elif kind == 'note': story.append(Paragraph(esc(val), note))
            elif kind in ('ul', 'ol'):
                items = [ListItem(Paragraph(esc(v), sty), leftIndent=12) for v in val]
                story.append(ListFlowable(items, bulletType='bullet' if kind == 'ul' else '1',
                                          start='•' if kind == 'ul' else 1, bulletFontName='DV',
                                          bulletFontSize=sty.fontSize, leftIndent=12))
                story.append(Spacer(1, 4))
            elif kind == 'table':
                cs = small if sty is small else st(fontSize=8, leading=10)
                hs = ParagraphStyle('th', parent=cs, fontName='DVB')
                data = [[Paragraph(esc(c), hs) for c in val[0]]] + [[Paragraph(esc(c), cs) for c in r] for r in val[1:]]
                t = Table(data, colWidths=[1.35 * inch, W - 1.2 * inch - 1.35 * inch])
                t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                       ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EDEDED')),
                                       ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#BBBBBB')),
                                       ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
                story += [t, Spacer(1, 6)]

    def page(c, d):
        if d.page == 1: 
            c.setFillColor(ACCENT); c.rect(0, H - 0.5 * inch, W, 0.5 * inch, stroke=0, fill=1); return
        c.setFont('DV', 7); c.setFillColor(GREY)
        c.drawString(0.6 * inch, 0.4 * inch, f'{BRAND} {MODEL}')
        c.drawRightString(W - 0.6 * inch, 0.4 * inch, str(d.page))
    doc = SimpleDocTemplate(os.path.join(OUT, 'manual.pdf'), pagesize=(W, H), leftMargin=0.6 * inch,
                            rightMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.65 * inch,
                            title=f'{BRAND} {MODEL} user manual')
    doc.build(story, onFirstPage=page, onLaterPages=page)

# ---------------------------------------------------------------- icons
def icon_rail(c, x, y, s):
    c.setStrokeColor(INK); c.setLineWidth(1)
    for i in range(7):  # keys
        c.rect(x + i * s / 7, y, s / 7, s * 0.45, stroke=1, fill=0)
    c.setFillColor(INK)
    for i in (0, 1, 3, 4, 5):
        c.rect(x + (i + 0.68) * s / 7, y + s * 0.18, s / 7 * 0.6, s * 0.27, stroke=0, fill=1)
    c.setFillColor(INK); c.roundRect(x, y + s * 0.5, s, s * 0.12, 2, stroke=0, fill=1)
    c.setFillColor(ACCENT)
    for i in (2, 5): c.circle(x + (i + 0.5) * s / 7, y + s * 0.56, s * 0.035, stroke=0, fill=1)
def icon_plug(c, x, y, s):
    c.setStrokeColor(INK); c.setFillColor(INK); c.setLineWidth(1.4)
    c.roundRect(x + s * 0.1, y + s * 0.35, s * 0.4, s * 0.3, 3, stroke=1, fill=0)      # charger
    c.rect(x + s * 0.18, y + s * 0.65, s * 0.06, s * 0.12, stroke=0, fill=1)
    c.rect(x + s * 0.36, y + s * 0.65, s * 0.06, s * 0.12, stroke=0, fill=1)
    p = c.beginPath(); p.moveTo(x + s * 0.3, y + s * 0.35); p.curveTo(x + s * 0.3, y, x + s * 0.8, y + s * 0.1, x + s * 0.8, y + s * 0.4)
    c.drawPath(p, stroke=1, fill=0)
    c.roundRect(x + s * 0.72, y + s * 0.4, s * 0.16, s * 0.12, 1.5, stroke=0, fill=1)   # USB-C plug
def icon_wifi(c, x, y, s):
    c.setStrokeColor(INK); c.setLineWidth(1.4)
    cx, cy = x + s / 2, y + s * 0.2
    for r in (0.18, 0.32, 0.46): c.arc(cx - s * r, cy - s * r, cx + s * r, cy + s * r, 45, 90)
    c.setFillColor(INK); c.circle(cx, cy + 1, s * 0.05, stroke=0, fill=1)
def icon_note(c, x, y, s):
    c.setFillColor(INK); c.setStrokeColor(INK); c.setLineWidth(1.6)
    c.ellipse(x + s * 0.2, y + s * 0.1, x + s * 0.42, y + s * 0.28, stroke=0, fill=1)
    c.ellipse(x + s * 0.58, y + s * 0.18, x + s * 0.8, y + s * 0.36, stroke=0, fill=1)
    c.line(x + s * 0.41, y + s * 0.2, x + s * 0.41, y + s * 0.85)
    c.line(x + s * 0.79, y + s * 0.28, x + s * 0.79, y + s * 0.93)
    c.setLineWidth(4); c.line(x + s * 0.41, y + s * 0.83, x + s * 0.79, y + s * 0.91)

# ---------------------------------------------------------------- quickstart.pdf (6 x 4 in, 2 sides)
def wrap(c, text, x, y, width, font='DV', size=8, leading=10):
    from reportlab.lib.utils import simpleSplit
    for line in simpleSplit(text, font, size, width):
        c.setFont(font, size); c.drawString(x, y, line); y -= leading
    return y
def quickstart():
    W, H = 6 * inch, 4 * inch
    c = canvas.Canvas(os.path.join(OUT, 'quickstart.pdf'), pagesize=(W, H))
    c.setTitle(f'{BRAND} quick start')
    # side 1
    c.setFillColor(ACCENT); c.rect(0, H - 0.42 * inch, W, 0.42 * inch, stroke=0, fill=1)
    c.setFillColor(INK); c.setFont('DVB', 14); c.drawString(0.25 * inch, H - 0.3 * inch, f'{BRAND}  ·  Quick start')
    steps = [(icon_rail, 'Place', 'Join the two rail halves with the joiner. Lay the rail on its felt feet just behind the keys. Arrow at middle C.'),
             (icon_plug, 'Power', 'Plug the USB-C cable into the end cap and a phone charger (5 V, 3 A recommended).'),
             (icon_wifi, 'Connect', f'On your phone, join Wi-Fi “{SSID}”. If no page opens, browse to 192.168.4.1'),
             (icon_note, 'Play', 'Calibrate once, upload a MIDI file, press Start and follow the lit keys.')]
    colw = (W - 0.5 * inch) / 4
    for i, (ic, title, txt) in enumerate(steps):
        x = 0.25 * inch + i * colw
        c.setFillColor(ACCENT); c.circle(x + 0.15 * inch, H - 0.7 * inch, 0.13 * inch, stroke=0, fill=1)
        c.setFillColor(INK); c.setFont('DVB', 11); c.drawCentredString(x + 0.15 * inch, H - 0.74 * inch, str(i + 1))
        c.setFont('DVB', 11); c.drawString(x + 0.35 * inch, H - 0.74 * inch, title)
        ic(c, x + 0.12 * inch, H - 1.75 * inch, 0.85 * inch)
        c.setFillColor(INK); wrap(c, txt, x + 0.05 * inch, H - 2.0 * inch, colw - 0.15 * inch, size=7.5, leading=9.5)
    c.setFillColor(GREY)
    wrap(c, ADAPTER_NOTE, 0.25 * inch, 0.32 * inch, W - 0.5 * inch, size=6.5, leading=8)
    c.showPage()
    # side 2
    c.setFillColor(INK); c.setFont('DVB', 12); c.drawString(0.25 * inch, H - 0.4 * inch, 'Need help?')
    y = H - 0.65 * inch
    for t in ['No lights: check the cable and that the joiner is fully pushed in.',
              'Dim or flickering: use a 5 V, 3 A charger, not a laptop port.',
              'Lights off the keys: Settings → Calibrate on the control page.',
              'Full manual, safety and FCC information: scan the code or see the printed manual.']:
        c.setFillColor(ACCENT); c.circle(0.32 * inch, y + 3, 2.2, stroke=0, fill=1)
        c.setFillColor(INK); y = wrap(c, t, 0.42 * inch, y, 3.6 * inch, size=8, leading=10) - 4
    qx, qy, qs = W - 1.65 * inch, H - 1.95 * inch, 1.35 * inch
    c.setDash(3, 2); c.setStrokeColor(GREY); c.rect(qx, qy, qs, qs); c.setDash()
    c.setFillColor(GREY); c.setFont('DV', 7)
    c.drawCentredString(qx + qs / 2, qy + qs / 2 + 4, 'QR → online manual URL')
    c.drawCentredString(qx + qs / 2, qy + qs / 2 - 6, MANUAL_URL)
    c.setFillColor(GREY); y = 1.1 * inch
    y = wrap(c, f'Contains FCC ID: {FCC_ID}. This device complies with part 15 of the FCC Rules; see the manual for the full statement.', 0.25 * inch, y, W - 0.5 * inch, size=6.5, leading=8)
    y = wrap(c, f'Indoor, dry use. Not a toy. {PARTY}', 0.25 * inch, y - 2, W - 0.5 * inch, size=6.5, leading=8)
    c.setFont('DVB', 7); c.drawString(0.25 * inch, 0.25 * inch, f'{BRAND} {MODEL} · Made in China')
    c.save()

# ---------------------------------------------------------------- labels.pdf
def crop(c, x, y, w, h, d=3 * mm):
    c.setStrokeColor(GREY); c.setLineWidth(0.25)
    for cx, cy, sx, sy in ((x, y, -1, -1), (x + w, y, 1, -1), (x, y + h, -1, 1), (x + w, y + h, 1, 1)):
        c.line(cx + sx * 1 * mm, cy, cx + sx * (1 * mm + d), cy); c.line(cx, cy + sy * 1 * mm, cx, cy + sy * (1 * mm + d))
def rating_label(c, x, y, k=1.0):
    w, h = 30 * mm * k, 15 * mm * k
    c.setStrokeColor(colors.lightgrey); c.setLineWidth(0.2); c.rect(x, y, w, h)
    c.setFillColor(INK)
    c.setFont('DVB', 5 * k); c.drawString(x + 1.2 * mm * k, y + h - 2.6 * mm * k, f'{BRAND}  {MODEL}')
    c.setFont('DV', 3.6 * k)
    lines = [f'Input: {POWER}', 'Contains FCC ID: [MODULE ID]', 'See manual for FCC statement', 'Made in China', 'SN: DK1-XXXXXX']
    yy = y + h - 4.7 * mm * k
    for l in lines: c.drawString(x + 1.2 * mm * k, yy, l); yy -= 1.85 * mm * k
    return w, h
def box_label(c, x, y):
    w, h = 4 * inch, 2 * inch
    c.setStrokeColor(colors.lightgrey); c.setLineWidth(0.3); c.rect(x, y, w, h)
    c.setFillColor(INK); c.setFont('DVB', 11); c.drawString(x + 8, y + h - 16, f'{BRAND}  {MODEL}')
    c.setFont('DV', 6.3)
    yy = y + h - 27
    yy = wrap(c, 'LED piano learning light. Contents: 2 rail halves, controller end cap, blank end cap, joiner, 2 feet, USB-C cable. Adapter not included.', x + 8, yy, 2.25 * inch, size=6.3, leading=7.6)
    yy = wrap(c, f'Input {POWER}. Contains FCC ID: [MODULE ID].', x + 8, yy - 2, 2.25 * inch, size=6.3, leading=7.6)
    yy = wrap(c, f'US responsible party: {PARTY}', x + 8, yy - 2, 2.25 * inch, size=6.3, leading=7.6)
    c.setFont('DVB', 8); c.drawString(x + 8, y + 8, 'Made in China')
    bx, by, bw, bh = x + w - 1.45 * inch, y + 0.35 * inch, 1.35 * inch, 1.0 * inch
    c.setDash(2, 2); c.setStrokeColor(GREY); c.rect(bx, by, bw, bh); c.setDash()
    c.setFillColor(GREY); c.setFont('DV', 6.5); c.drawCentredString(bx + bw / 2, by + bh / 2 + 2, 'UPC-A from GS1 US')
    c.drawCentredString(bx + bw / 2, by + bh / 2 - 7, '(barcode placeholder)')
    c.setFont('DV', 6); c.drawCentredString(bx + bw / 2, by - 9, 'FNSKU label goes here if sold via FBA')
def labels():
    W, H = 8.5 * inch, 11 * inch
    c = canvas.Canvas(os.path.join(OUT, 'labels.pdf'), pagesize=(W, H)); c.setTitle(f'{BRAND} labels')
    c.setFont('DVB', 12); c.setFillColor(INK); c.drawString(0.75 * inch, H - 0.75 * inch, f'{BRAND} {MODEL} — labels (print at 100%, no scaling)')
    c.setFont('DVB', 9); c.drawString(0.75 * inch, H - 1.2 * inch, 'A. Product rating label — controller end cap, 30 × 15 mm, actual size')
    w, h = rating_label(c, 0.75 * inch, H - 1.95 * inch); crop(c, 0.75 * inch, H - 1.95 * inch, w, h)
    c.setFont('DV', 8); c.drawString(0.75 * inch, H - 2.3 * inch, 'Same label at 4× for proofing:')
    rating_label(c, 0.75 * inch, H - 4.85 * inch, 4.0)
    c.setFont('DV', 7.5); c.setFillColor(GREY)
    y = wrap(c, 'Material: white or silver polyester (PET), permanent adhesive, laser or thermal-transfer print; ≥ 3.6 pt type. '
             'Replace [MODULE ID] with the real FCC ID from the controller supplier (e.g. an Espressif module ID — confirm). '
             'Serial number: sequential DK1-000001… printed by the assembly partner. 47 CFR 15.19(a)(5) allows the full part 15 '
             'statement to go in the manual and on the box when the device is too small; confirm label layout with the test lab.',
             0.75 * inch, H - 5.15 * inch, 7 * inch, size=7.5, leading=9.5)
    c.setFillColor(INK); c.setFont('DVB', 9); c.drawString(0.75 * inch, H - 6.0 * inch, 'B. Box information label — 4 × 2 in, actual size')
    box_label(c, 0.75 * inch, H - 8.3 * inch); crop(c, 0.75 * inch, H - 8.3 * inch, 4 * inch, 2 * inch)
    c.setFont('DV', 7.5); c.setFillColor(GREY)
    wrap(c, 'Apply to the bottom panel or one end of the shipper box if the barcode is not printed on the box itself. '
         'Get the UPC-A from GS1 US (Amazon checks the GS1 database).', 0.75 * inch, H - 8.65 * inch, 7 * inch, size=7.5, leading=9.5)
    c.save()

# ---------------------------------------------------------------- box dieline + artwork (SVG, mm)
def box_svg():
    Lb, Wb, Db = 660.4, 101.6, 76.2      # inside dims (26 x 4 x 3 in)
    F = Db / 2                           # end-flap depth (flaps close the 4 x 3 in ends)
    G = 35.0                             # glue flap
    M = 20.0                             # sheet margin
    X0 = M + F; X1 = X0 + Lb             # body x-range
    # panel stack top→bottom: glue, TOP (W), FRONT (D), BOTTOM (W), BACK (D)
    ys = [M]; 
    for hgt in (G, Wb, Db, Wb, Db): ys.append(ys[-1] + hgt)
    names = ['GLUE', 'TOP', 'FRONT', 'BOTTOM', 'BACK']
    SW = X1 + F + M; SH = ys[-1] + M + 60
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW}mm" height="{SH}mm" viewBox="0 0 {SW} {SH}">')
    a(f'<rect x="0" y="0" width="{SW}" height="{SH}" fill="white"/>')
    # artwork fills (under lines) with 3.175 mm (1/8 in) bleed beyond the panel
    bl = 3.175
    a(f'<rect x="{X0-F-bl}" y="{ys[1]-bl}" width="{Lb+2*F+2*bl}" height="{ys[5]-ys[1]+2*bl}" fill="#151515"/>')
    def text(x, y, s, size, weight='normal', fill='white', anchor='start'):
        a(f'<text x="{x:.2f}" y="{y:.2f}" font-family="Helvetica" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{html.escape(s)}</text>')
    def keys(x, y, w, h, lit):
        n = 21; kw = w / n
        for i in range(n):
            col = '#F2A900' if i in lit else '#F4F4F4'
            a(f'<rect x="{x+i*kw:.2f}" y="{y:.2f}" width="{kw:.2f}" height="{h:.2f}" fill="{col}" stroke="#151515" stroke-width="0.4"/>')
        for i in range(n - 1):
            if i % 7 in (2, 6): continue
            a(f'<rect x="{x+(i+0.68)*kw:.2f}" y="{y:.2f}" width="{kw*0.64:.2f}" height="{h*0.6:.2f}" fill="#151515"/>')
        a(f'<rect x="{x:.2f}" y="{y-5:.2f}" width="{w:.2f}" height="3" fill="#2A2A2A"/>')
        for i in lit:
            a(f'<circle cx="{x+(i+0.5)*kw:.2f}" cy="{y-3.5:.2f}" r="1.6" fill="#F2A900"/>')
    # TOP panel
    yT = ys[1]; text(X0 + 18, yT + 42, BRAND, 30, 'bold'); text(X0 + 18, yT + 58, 'LED piano learning light', 10, fill='#F2A900')
    text(X0 + 18, yT + 72, 'For any piano — acoustic or digital. No app, no MIDI cable.', 7.5, fill='#DDDDDD')
    keys(X0 + 330, yT + 30, 300, 50, {4, 9, 15})
    # FRONT panel
    yF = ys[2]; text(X0 + 18, yF + 33, BRAND, 20, 'bold'); text(X0 + 18, yF + 48, 'Follow the lights. Play the song.', 9, fill='#F2A900')
    text(X0 + 18, yF + 61, f'Model {MODEL}', 7, fill='#BBBBBB'); keys(X0 + 300, yF + 22, 330, 40, {2, 7, 11, 18})
    # BACK panel — features
    yB = ys[4]; text(X0 + 18, yB + 20, 'Why you will like it', 9, 'bold', '#F2A900')
    feats = ['Works on acoustic and digital pianos', 'No app, no account, no MIDI cable — just your phone browser',
             'Upload any MIDI file and follow the lit keys', 'Sits behind the keys on felt feet: nothing stuck to your piano',
             'Powered by a USB-C phone charger (5 V, 3 A recommended)']
    for i, f in enumerate(feats):
        a(f'<circle cx="{X0+20:.2f}" cy="{yB+31+i*9.5:.2f}" r="1.3" fill="#F2A900"/>'); text(X0 + 25, yB + 33 + i * 9.5, f, 6.5, fill='#EEEEEE')
    keys(X0 + 400, yB + 22, 230, 36, {3, 10, 16})
    # BOTTOM panel — contents, compliance, barcode
    yBo = ys[3]; text(X0 + 18, yBo + 16, 'In the box', 7.5, 'bold', '#F2A900')
    for i, cline in enumerate(CONTENTS): text(X0 + 18, yBo + 26 + i * 7.2, '• ' + cline, 5.2, fill='#EEEEEE')
    text(X0 + 18, yBo + 26 + 6 * 7.2 + 2, ADAPTER_NOTE, 4.6, fill='#BBBBBB')
    cx = X0 + 300
    comp = [f'{BRAND} {MODEL} · Input 5 V DC, 3 A max (USB-C)', f'Contains FCC ID: {FCC_ID}',
            'This device complies with part 15 of the FCC Rules. Operation is subject to the following two conditions:',
            '(1) This device may not cause harmful interference, and (2) this device must accept any interference',
            'received, including interference that may cause undesired operation.',
            f'US responsible party: {PARTY}', 'Indoor use only. Not a toy. Read the manual before use.']
    for i, cline in enumerate(comp): text(cx, yBo + 16 + i * 7, cline, 4.6, fill='#EEEEEE')
    text(cx, yBo + 16 + 7 * 7 + 4, 'MADE IN CHINA', 7, 'bold')
    a(f'<rect x="{X1-95:.2f}" y="{yBo+18:.2f}" width="80" height="50" fill="white"/>')
    text(X1 - 55, yBo + 42, 'UPC-A barcode', 5.5, fill='#555555', anchor='middle'); text(X1 - 55, yBo + 50, '(from GS1 US)', 5, fill='#555555', anchor='middle')
    # END flaps: small brand on each major (W-panel) flap
    for xx in (X0 - F / 2, X1 + F / 2):
        for yy in (ys[1] + Wb / 2, ys[3] + Wb / 2):
            a(f'<text x="{xx:.2f}" y="{yy:.2f}" font-family="Helvetica" font-size="5.5" font-weight="bold" fill="white" text-anchor="middle" transform="rotate(-90 {xx:.2f} {yy:.2f})">{html.escape(BRAND)}</text>')
    # ---- dieline: cut = solid red, fold = dashed blue
    cut = 'stroke="#E00000" stroke-width="0.35" fill="none"'
    fold = 'stroke="#0050FF" stroke-width="0.35" stroke-dasharray="3,2" fill="none"'
    slot = 3.0
    # glue flap (tapered)
    a(f'<path d="M {X0} {ys[1]} L {X0+12} {ys[0]} L {X1-12} {ys[0]} L {X1} {ys[1]}" {cut}/>')
    a(f'<line x1="{X0}" y1="{ys[1]}" x2="{X1}" y2="{ys[1]}" {fold}/>')
    for i in range(1, 5):
        top, bot = ys[i], ys[i + 1]
        t2 = top + (slot / 2 if i > 1 else 0); b2 = bot - (slot / 2 if i < 4 else 0)
        # left and right end flaps
        a(f'<path d="M {X0} {t2} L {X0-F} {t2} L {X0-F} {b2} L {X0} {b2}" {cut}/>')
        a(f'<path d="M {X1} {t2} L {X1+F} {t2} L {X1+F} {b2} L {X1} {b2}" {cut}/>')
        a(f'<line x1="{X0}" y1="{top}" x2="{X0}" y2="{bot}" {fold}/>'); a(f'<line x1="{X1}" y1="{top}" x2="{X1}" y2="{bot}" {fold}/>')
        if i < 4:
            a(f'<line x1="{X0}" y1="{bot}" x2="{X1}" y2="{bot}" {fold}/>')
            a(f'<line x1="{X0-F}" y1="{bot-slot/2}" x2="{X0}" y2="{bot-slot/2}" stroke="none"/>')
    a(f'<line x1="{X0}" y1="{ys[5]}" x2="{X1}" y2="{ys[5]}" {cut}/>')
    # panel names + dims (outside artwork, small, for the printer)
    for i, n in enumerate(names):
        a(f'<text x="{X1+F+6:.2f}" y="{(ys[i]+ys[i+1])/2:.2f}" font-family="Helvetica" font-size="3.5" fill="#E00000">{n}</text>')
    notes = [f'{BRAND} {MODEL} shipper box — RSC, end-loading. Inside 660.4 × 101.6 × 76.2 mm (26 × 4 × 3 in). Units: mm. Flat size ≈ {Lb+2*F:.1f} × {ys[5]-ys[0]:.1f} mm.',
             'Red solid = cut. Blue dashed = fold. Artwork carries 3.175 mm (1/8 in) bleed. Flap slots 3 mm. Board: E/B-flute white, print outside.',
             'Panels: TOP 26×4 in, FRONT/BACK 26×3 in, BOTTOM 26×4 in (contents, compliance, barcode); end flaps close the 4×3 in ends.',
             'PLACEHOLDER layout: the printer\'s own dieline template (with caliper allowances) governs final dimensions. Brand, FCC ID, company and UPC are placeholders.']
    for i, n in enumerate(notes):
        a(f'<text x="{M}" y="{ys[5]+14+i*8:.2f}" font-family="Helvetica" font-size="4.6" fill="#333333">{html.escape(n)}</text>')
    a('</svg>')
    path = os.path.join(OUT, 'box-artwork.svg'); open(path, 'w').write("\n".join(o))
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    renderPDF.drawToFile(svg2rlg(path), os.path.join(OUT, 'box-artwork.pdf'))

if __name__ == '__main__':
    manual_md(); manual_pdf(); quickstart(); labels(); box_svg(); print('built into', OUT)
