# -*- coding: utf-8 -*-
"""P10 on its own: what was found, what was printed, and what was read."""
import csv, os, sys
from PIL import Image, ImageDraw, ImageFont
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
import capt
import numpy as np
import axis_reader as A
import y_scale_group as Y

OK=(0,150,110); BAD=(168,52,43); GEOM=(10,90,175)
MONO="/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

def render(png, box, spine, out, scale=3, pad=8):
    img=Image.open(os.path.join(ROOT,"clips",png))
    _a,dark=A._dark(img)
    run=A.spine_run(dark,spine,box[2],box[3])
    ticks=Y.tick_rows(dark,box,spine,run,"LEFT")
    lo=max(0,spine-A.LABEL_BAND_MAX)
    crop=img.convert("RGB").crop((lo-pad, box[2]-pad, spine+14, box[3]+pad))
    crop=crop.resize((crop.width*scale, crop.height*scale), Image.LANCZOS)
    d=ImageDraw.Draw(crop)
    f=ImageFont.truetype(MONO, 22)
    ox,oy=lo-pad, box[2]-pad
    for y in ticks:
        yy=(y-oy)*scale
        d.line([(0,yy),(crop.width,yy)], fill=OK, width=2)
        d.text((6,yy-26), "tick %d"%y, font=f, fill=OK)
    d.line([((box[0]-ox)*scale,0),((box[0]-ox)*scale,crop.height)], fill=GEOM, width=3)
    d.text(((box[0]-ox)*scale+6, 6), "box left edge x=%d"%box[0], font=f, fill=GEOM)
    d.line([((spine-ox)*scale,0),((spine-ox)*scale,crop.height)], fill=BAD, width=3)
    lines=["box            %d,%d,%d,%d   origin COLUMN_SIBLING"%tuple(box),
           "axis_geometry  ANCHOR_FREE  -  one free candidate at x=%d, run %d-%d"%(spine,run[0],run[1]),
           "tick rows      %s"%", ".join(str(t) for t in ticks),
           "numerals       printed 4 3 2 1   read 1, at y=1069.3",
           "shadow ladder  only 1 label(s); 3 needed to check a ladder",
           "",
           "축 기하는 정확하고 박스도 숫자를 자르지 않는다. 이 행의 라벨이 한 자리 숫자다."]
    crop=capt.below(crop, "177 Fig. 2 P10: 공유축으로 설명되지 않는 하나", lines, minw=1100)
    crop.save(out); return out

if __name__=="__main__":
    print(render("ID177__fig2.png",(210,439,840,1072),239,"png/F3_p10_diagnosis.png"))
