"""Write a real WebPlotDigitizer .tar project from extracted calibration + points.

`WPD_Project_File` is provenance only if the file exists and opens. Declaring a
name for a project nobody saved records a promise, not a record - and the
validator now checks the path is on disk, so the promise has to be kept.
"""
import io
import json
import os
import tarfile


def _tar_add(tf, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def write_project(path, image_path, axes, datasets, project_name=None):
    """axes: [{name, calibrationPoints:[{px,py,dx,dy}], isLogX, isLogY}]
       datasets: [{name, axesName, data:[{x,y,value}]}]"""
    project_name = project_name or os.path.splitext(os.path.basename(path))[0]
    img = os.path.basename(image_path)
    wpd = {"version": [4, 2],
           "axesColl": [dict(name=a["name"], type="XYAxes",
                             isLogX=bool(a.get("isLogX")), isLogY=bool(a.get("isLogY")),
                             noRotation=None,
                             calibrationPoints=[dict(px=p["px"], py=p["py"],
                                                     dx=str(p.get("dx", "")),
                                                     dy=str(p.get("dy", "")), dz=None)
                                                for p in a["calibrationPoints"]])
                        for a in axes],
           "datasetColl": [dict(name=d["name"], axesName=d["axesName"],
                                colorRGB=[200, 0, 0, 255], metadataKeys=[],
                                data=[dict(x=pt["x"], y=pt["y"], metadata=None,
                                           value=pt.get("value"))
                                      for pt in d["data"]],
                                autoDetectionData=None)
                           for d in datasets],
           "measurementColl": []}
    info = {"version": [4, 0], "json": "wpd.json", "images": [img]}
    with tarfile.open(path, "w") as tf:
        _tar_add(tf, project_name + "/info.json", json.dumps(info).encode())
        _tar_add(tf, project_name + "/wpd.json", json.dumps(wpd).encode())
        with open(image_path, "rb") as fh:
            _tar_add(tf, project_name + "/" + img, fh.read())
    return path
