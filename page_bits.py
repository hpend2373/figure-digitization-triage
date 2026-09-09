# -*- coding: utf-8 -*-
"""사람에게 보여 주는 페이지들이 함께 쓰는 조각.

`errorbar_review_page`와 `worklist_page`가 같은 화면처럼 보여야 하고, 같은
글자 escape를 써야 합니다. 두 벌로 두면 한쪽만 고쳐질 때 두 페이지가 서로
다르게 보이고, 더 나쁘게는 한쪽에서만 인용문이 속성 밖으로 샙니다.
"""
import base64
import io
import os

#: 크롭을 페이지에 싣는 크기. 오차 막대가 무엇인지 보려면 막대가 보여야 하고,
#: 78개를 원본 크기로 실으면 브라우저가 열지 못합니다.
THUMB = (560, 560)


def esc(text):
    return (str(text if text is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


#: 할 일 목록이 싣는 크기. 여기서는 그림을 알아보기만 하면 되고, 334장을
#: 판정 페이지 크기로 실으면 파일이 열 배가 됩니다.
THUMB_SMALL = (260, 260)


def thumb(path, size=None):
    """크롭 한 장을 data URL로. 못 읽으면 빈 문자열 - 없는 그림은 없다고 둡니다."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        from PIL import Image
    except Exception:                                   # pragma: no cover
        return ""
    try:
        im = Image.open(path)
        im.thumbnail(size or THUMB)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72)
    except Exception:                                   # noqa: BLE001
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


CSS = """<style>
body{font:15px/1.6 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;
margin:0;background:#f4f4f2;color:#1a1a1a}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #d8d8d4;
padding:14px 20px;z-index:5}
h1{font-size:17px;margin:0 0 4px}
.note{color:#5a5a56;font-size:13px;margin:6px 0 0;max-width:80ch}
main{padding:20px;max-width:1180px;margin:0 auto}
h3.sec{font-size:15px;margin:26px 0 2px;padding-top:8px;border-top:2px solid #ddddd6}
.sec-why{margin:0 0 12px}
.doc{background:#fff;border:1px solid #ddddd8;border-radius:8px;margin:0 0 22px;
padding:16px 18px}
.doc.done{border-color:#6b8f6b;background:#f6faf6}
h2{font-size:14px;margin:0 0 2px;font-family:ui-monospace,Menlo,monospace;
word-break:break-all}
.sub{color:#66665f;font-size:13px;margin:0 0 12px}
.figs{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 14px}
.fig{border:1px solid #e2e2dd;border-radius:6px;padding:6px;background:#fbfbfa}
.fig img{display:block;max-width:270px;height:auto;border-radius:3px}
.fig .nofig{width:120px;height:60px;display:flex;align-items:center;
justify-content:center;color:#9a9a92;font-size:12px}
.fig .cap{font-size:12px;color:#55554f;margin-top:5px}
.cand{border:1px solid #e2e2dd;border-radius:6px;padding:10px 12px;margin:0 0 9px;
background:#fbfbfa}
.cand.ok{border-color:#b7d3b9}
.cand.picked{border-color:#3b6ea5;background:#f2f7fd}
.cand.own{display:block;font-size:13px;color:#55554f}
blockquote{margin:6px 0;padding:8px 11px;background:#fff;border-left:3px solid #c9c9c2;
font-size:14px;white-space:pre-wrap}
.meta{font-size:12px;color:#55554f;margin-top:4px}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;
border:1px solid;margin-right:6px;vertical-align:1px}
.ok{color:#2f6b34;border-color:#9dc4a0;background:#eef7ef}
.warn{color:#8a5a12;border-color:#dcc08a;background:#fdf6e9}
.row{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-top:12px;
padding-top:12px;border-top:1px solid #eeeee9}
label{font-size:13px}
.verify{padding:3px 8px;border:1px solid #dcc08a;border-radius:5px;background:#fdf6e9}
select,input[type=text]{font:13px inherit;padding:5px 7px;border:1px solid #c9c9c2;
border-radius:4px;background:#fff}
.state{font-size:13px;color:#8a5a12;margin-top:9px}
.state.ready{color:#2f6b34}
button{font:14px inherit;padding:8px 15px;border:1px solid #b9b9b2;border-radius:5px;
background:#fff;cursor:pointer}
button:hover{background:#f2f2ee}
.count{font-variant-numeric:tabular-nums;color:#55554f;font-size:13px;font-weight:400}
</style></head><body>"""
