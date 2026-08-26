# -*- coding: utf-8 -*-
"""A caption bar under a rendered figure, in Korean or in monospace.

Reconstructed and COMMITTED this time. The first version lived only in the
working directory, and when the container was reclaimed every renderer in this
folder stopped running from a clean checkout - which is the same class of loss
as the caption scan, and the same fix: put it in the repository.
"""
from PIL import Image, ImageDraw, ImageFont

CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
CJKR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
BG, INK, MUTE = (247, 249, 247), (23, 29, 26), (95, 109, 102)


def kr(s, bold=True):
    """Noto Sans CJK, index 1 - the Korean face inside the collection."""
    return ImageFont.truetype(CJK if bold else CJKR, s, index=1)


def mono(s):
    return ImageFont.truetype(MONO, s)


def wrap(t, f, w):
    out, cur = [], ""
    for word in t.split(' '):
        trial = (cur + ' ' + word).strip()
        if f.getlength(trial) <= w or not cur:
            cur = trial
        else:
            out.append(cur); cur = word
    if cur:
        out.append(cur)
    return out


def below(im, title, lines, keys=(), pad=28, minw=1560):
    """`im` with a caption bar under it: a title, monospace lines, and a key.

    A line holding any Hangul syllable is set in the Korean face; everything
    else is monospace, because the lines are usually tables of numbers and a
    proportional face makes a table stop being one.
    """
    W = max(im.width, minw)
    tf, lf, kb = kr(29), mono(19), kr(20, False)
    tl = wrap(title, tf, W - 2 * pad)
    h = pad + len(tl) * 40 + len(lines) * 28 + (36 if keys else 0) + pad
    out = Image.new("RGB", (W, im.height + h), BG)
    out.paste(im, ((W - im.width) // 2, 0))
    d = ImageDraw.Draw(out)
    y = im.height + pad
    for l in tl:
        d.text((pad, y), l, font=tf, fill=INK); y += 40
    for l in lines:
        use = kb if any('가' <= ch <= '힣' for ch in l) else lf
        d.text((pad, y), l, font=use, fill=MUTE); y += 28
    if keys:
        y += 6
        x = pad
        kf = kr(18, False)
        for col, name, dashed in keys:
            if dashed:
                for i in range(0, 18, 7):
                    d.line([(x + i, y + 10), (x + min(i + 4, 18), y + 10)],
                           fill=col, width=4)
            else:
                d.rectangle([x, y + 3, x + 16, y + 17], outline=col, width=3)
            d.text((x + 24, y), name, font=kf, fill=MUTE)
            x += 24 + int(kf.getlength(name)) + 26
    return out
