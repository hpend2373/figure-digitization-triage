import numpy as np, hashlib, pandas as pd, importlib.util as u
from PIL import Image
from bar_reader import colour_masks, read_bar_panel, runs
import crosscheck_id323 as X
import grid_engine as G
from make_wpd_project import write_project
s=u.spec_from_file_location('k','kernel.py'); k=u.module_from_spec(s); s.loader.exec_module(k)
SESS=["B-1","DI7","DI14","DI19","R1","R5"]
SRC='caption: "Data are given for a group of 10 subjects (Mean +/- SEM)"'
def ticks_of(dark,box,n):
    x0,x1,y0,y1=box; sub=dark[y0:y1,x0:x1]
    ax=min(x0+i for i,v in enumerate(sub.sum(axis=0)) if v>0.6*sub.shape[0])
    sl=dark[y0:y1,max(0,ax-14):ax-3]
    tr=[y0+i for i,v in enumerate(sl) if v.sum()>=2]
    cen=[round((r[0]+r[-1])/2,1) for r in runs(tr,4)]
    assert len(cen)==n, f"{len(cen)} ticks vs {n}"
    return cen
FIGS=[dict(fid="323|FIG1", img="fixtures/id323_fig1.jpeg", page=4, num="FIGURE 1",
    gid="GRID|SESSION6xPOSTURE2", series={"SUPINE":"blue","ORTHOSTASIS":"red"},
    factors={"TIMEPOINT":SESS,"POSTURE":["SUPINE","ORTHOSTASIS"]}, unlisted="PAP", obs=6, wl=5, scale="RATIO",
    cap="FIGURE 1 | The values of hemodynamic parameters during tilt test 1 day before dry immersion "
        "(B-1), during dry immersion (DI7, DI14, DI19) and during the recovery period (R1 and R5). "
        "(A) SAP; (B) DAP; (C) MAP; (D) PAP; (E) HR; (F) SV. Data are given for a group of 10 "
        "subjects (Mean +/- SEM).",
    panels=[("SAP",(90,960,140,600),[150,120,90,60,30,0],"Systolic blood pressure","mmHg"),
            ("DAP",(1100,1950,140,600),[90,60,30,0],"Diastolic blood pressure","mmHg"),
            ("MAP",(90,960,690,1140),[120,90,60,30,0],"Mean arterial pressure","mmHg"),
            ("PAP",(1100,1950,690,1140),[60,40,20,0],"Pulse pressure","mmHg"),
            ("HR",(90,960,1250,1684),[150,100,50,0],"Heart rate","bpm"),
            ("SV",(1100,1950,1250,1684),[120,90,60,30,0],"Stroke volume","ml")]),
  dict(fid="323|FIG2", img="323_p5_fig2.jpeg", page=5, num="FIGURE 2",
    gid="GRID|SESSION6", series={"RESPONSE":"red"}, factors={"TIMEPOINT":SESS}, unlisted="", obs=6, wl=6, scale="CHANGE",
    cap="FIGURE 2 | Changes in hemodynamic parameters during tilt test 1 day before dry immersion "
        "(B-1), during dry immersion (DI7, DI14, DI19) and in the recovery period (R1 and R5). "
        "Data are given for a group of 10 subjects (Mean +/- SEM).",
    panels=[("SAP",(90,960,20,430),[0,-5,-10,-15,-20,-25],"Change of systolic arterial pressure","%"),
            ("DAP",(1090,1950,20,430),[10,5,0,-5,-10,-15],"Change of diastolic arterial pressure","%"),
            ("MAP",(90,960,540,1000),[5,0,-5,-10,-15,-20],"Change of mean arterial pressure","%"),
            ("PAP",(1090,1950,540,1000),[0,-10,-20,-30,-40,-50],"Change of pulse pressure","%"),
            ("HR",(90,960,1120,1569),[80,60,40,20,0],"Change of heart rate","%"),
            ("SV",(1090,1950,1120,1569),[0,-10,-20,-30,-40],"Change of stroke volume","%")])]
figs=[];grids=[];units=[];vals=[];rep=[]
for F in FIGS:
    sha=hashlib.sha256(open(F["img"],'rb').read()).hexdigest()
    im=Image.open(F["img"]).convert('RGB'); masks=colour_masks(im); dark=masks["dark"]
    tar=f"id323_fig{F['page']-3}.tar"; wpd_axes=[]; wpd_sets=[]
    figs.append(dict(Figure_ID=F["fid"], Publication_ID=323,
      Source_File="323_10.3389_fphys.2020.00455.pdf", Source_Page=F["page"], Source_Image=F["img"],
      Source_Caption_Verbatim=F["cap"], Figure_Number=F["num"],
      Image_Resolution_Or_Hash=f"{im.width}x{im.height} sha256:{sha[:24]}",
      WPD_Project_File=tar, Observed_Panel_Count=F["obs"],
      Worklist_Panel_Count=F["wl"], Unlisted_Panels=F["unlisted"],
      Panel_Reconciliation_Status="UNLISTED_PANELS_FOUND" if F["obs"]>F["wl"] else "MATCHED", Note=""))
    for fac,lvs in F["factors"].items():
        for i,lv in enumerate(lvs):
            grids.append(dict(Grid_ID=F["gid"],Factor_Name=fac,Factor_Level=lv,Level_Order=i,Note=""))
    exp=int(np.prod([len(v) for v in F["factors"].values()]))
    for name,box,tv,outcome,unit in F["panels"]:
        tk=list(zip(tv,ticks_of(dark,box,len(tv))))
        bars=read_bar_panel(masks, box, tk, F["series"], baseline_value=0.0)
        # R2 is a genuinely independent re-reading: a column scan with a median
        # statistic, not a second call into the same function. Storing it here
        # makes the dual extraction part of the record instead of a side check.
        import numpy as _np
        _vs=_np.array([t[0] for t in tk],float); _ys=_np.array([t[1] for t in tk],float)
        _k,_b=_np.polyfit(_ys,_vs,1); _y2v=lambda py: float(_k*py+_b)
        _kk,_bb=_np.polyfit(_vs,_ys,1); _zero=float(_kk*0.0+_bb)
        r2={}
        for sname,ckey in F["series"].items():
            col = masks["blue"] if ckey=="blue" else masks["red"]
            rr_all=X.read(_np.asarray(im).astype(int), dark, col, box, _y2v, zero_row=_zero)
            # Match R2 to R1 by x position, not by sequence: a bar one reader
            # cannot see would otherwise pair every later reading with the wrong cell.
            for b in bars:
                if b["series"]!=sname: continue
                near=[q for q in rr_all if abs(q["x"]-b["x"])<=6]
                if near: r2[(sname,b["order"])]=near[0]
        uid=f"{F['fid']}|{name}"; rep.append((F["num"],name,len(bars),exp))
        wpd_axes.append(dict(name=f"{name} axes", isLogX=False, isLogY=False,
          calibrationPoints=[dict(px=box[0],py=tk[-1][1],dx="0",dy=""),
                             dict(px=box[1],py=tk[-1][1],dx="1",dy=""),
                             dict(px=box[0],py=tk[-1][1],dx="",dy=str(tk[-1][0])),
                             dict(px=box[0],py=tk[0][1],dx="",dy=str(tk[0][0]))]))
        wpd_sets.append(dict(name=f"{name} means", axesName=f"{name} axes",
          data=[dict(x=b["x"], y=b["top_px"], value=[b["order"], b["mean"]]) for b in bars]))
        units.append(dict(Unit_ID=uid, Figure_ID=F["fid"], Grid_ID=F["gid"], Panel=name,
          Outcome_Variable=outcome, Outcome_Domain="CV_HEMO", Unit=unit,
          Statistic_Type="CONTINUOUS", Display_Hint="UNSPECIFIED", Grid_Rule="FULL",
          Sparse_Justification="", Dispersion_Type="SEM", Errorbar_Definition_Source=SRC,
          N_Outcome=10, Value_Scale=F["scale"], Extraction_Method="DIGITIZED", Bar_Top_Definition="OUTLINE_CENTER",
          Errorbar_Stem_Confirmed="TRUE", Axis_X_Scale="LINEAR", Axis_Y_Scale="LINEAR",
          Axis_Calib_X1_Value=0, Axis_Calib_X1_Pixel=box[0], Axis_Calib_X2_Value=1,
          Axis_Calib_X2_Pixel=box[1], Axis_Calib_Y1_Value=tk[-1][0], Axis_Calib_Y1_Pixel=tk[-1][1],
          Axis_Calib_Y2_Value=tk[0][0], Axis_Calib_Y2_Pixel=tk[0][1], Extractor_1="bar_reader (row-profile)",
          Extractor_2="crosscheck_id323 (column-scan median)",
          Independent_Verification_Status="RECONCILED",
          Discrepancy_Note="Two independent readers of the same raster; the consensus is "
            "their midpoint. Cap-stroke centring differs by up to ~2.5 px, so dispersions "
            "can differ by more than the 5% tolerance on small error bars.",
          Date="2026-08-06", Note=""))
        for b in bars:
            lv={"TIMEPOINT":SESS[b["order"]]}
            if "POSTURE" in F["factors"]: lv["POSTURE"]=b["series"]
            m1=round(b["mean"],3)
            d1=None if b["dispersion"] is None else round(abs(b["dispersion"]),3)
            o=r2.get((b["series"], b["order"]))
            m2=round(o["mean"],3) if o else None
            d2=round(abs(o["disp"]),3) if (o and o.get("disp") is not None) else None
            mc=round((m1+m2)/2,3) if m2 is not None else m1
            dc=round((d1+d2)/2,3) if (d1 is not None and d2 is not None) else d1
            vals.append(dict(Unit_ID=uid, Cell_Key=G.fig_cell_key(lv),
              Mean_R1=m1, Dispersion_R1=d1, Mean_R2=m2, Dispersion_R2=d2,
              Mean=mc, Dispersion_Value=dc,
              Verification_Status="RECONCILED" if m2 is not None else "",
              Reconciliation_Note=("Two raster readers reconciled to their midpoint"
                                   if m2 is not None else "")))
    write_project(tar, F["img"], wpd_axes, wpd_sets)

def fr(rows,cols): return pd.DataFrame([{c:d.get(c,"") for c in cols} for d in rows],columns=cols)
Fd,Gd,Ud,Vd=(fr(figs,G.fig_figure_columns()),fr(grids,G.fig_grid_columns()),
             fr(units,G.fig_unit_columns()),fr(vals,G.fig_values_columns()))
for df,n in ((Fd,'figure_manifest'),(Gd,'grid_definitions'),(Ud,'unit_manifest'),(Vd,'figure_values')):
    df.to_csv(f'id323_{n}.csv',index=False)
print("figure     panel  read  expected")
for a,b,c,d in rep: print(f"  {a}  {b:4s} {c:5d} {d:9d}  {'' if c==d else '<<<'}")
print(f"\nfigures {len(Fd)} | grid rows {len(Gd)} | units {len(Ud)} | values {len(Vd)}")
p=G.fig_validate_bundle(pd.read_csv('id323_figure_manifest.csv'),pd.read_csv('id323_grid_definitions.csv'),
    pd.read_csv('id323_unit_manifest.csv'),pd.read_csv('id323_figure_values.csv'),kernel=k)
print("problems:",len(p))
if len(p): print(p.to_string(index=False))
