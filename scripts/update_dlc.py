"""DLC（アドオン）の一覧を取る。対象は data/dlc_targets.json の作品だけ（試験中）。
作品のストアページに載っているアドオン一覧（名前・価格・セール）を data/dlc.json に保存する。"""
import time
from common import *

targets = load_json("dlc_targets.json", [])
out = load_json("dlc.json", {})
T = today()
for gid in targets:
    try:
        st = preloaded(http(STORE.format(loc="ja-JP", id=gid)).decode())
    except Exception as e:
        print("dlc failed:", gid, e, flush=True)
        continue
    cd = st["core2"]["channels"]["channelData"]
    ps = st["core2"]["products"]["productSummaries"]
    key = next((k for k in cd if k.startswith("PRODUCTADDONS")), None)
    items = []
    for x in (cd[key]["data"]["products"] if key else []):
        p = ps.get(x["productId"]) or {}
        pr = ((p.get("specificPrices") or {}).get("purchaseable") or [{}])[0]
        now, msrp = pr.get("listPrice"), pr.get("msrp")
        off = round(pr.get("discountPercentage") or 0)
        end = (pr.get("endDateUtc") or "").split(" ")[0] if off else ""
        if end.startswith("12/30/9998"):
            end = ""
        items.append([x["productId"], p.get("title") or "", now, msrp, off, end])
    out[gid] = {"at": T, "items": items}
    print("dlc:", gid, len(items), flush=True)
    time.sleep(1)
for gid in list(out):
    if gid not in targets:
        del out[gid]
save_json("dlc.json", out)
