"""発売日がWebストアのデータに入っていない「発売予定」の作品だけ、Xboxアプリと同じ商品データベース
（displaycatalog）から発売日を補う。結果は data/release_dates.json {作品ID: "YYYY-MM-DD"（日本時間）}。
build.py は、ストアのデータに発売日がないときだけこれを使う。"""
import datetime
import json
import time
from common import http, load_json, save_json, load_jsonl

DC = "https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={ids}&market=JP&languages=ja-jp"


def jst_date(s):
    try:
        t = datetime.datetime.fromisoformat(s[:19]) + datetime.timedelta(hours=9)
    except ValueError:
        return None
    d = t.strftime("%Y-%m-%d")
    return d if "2000" < d < "2100" else None  # 未定のときの仮の日付（2100年など）は使わない


def main():
    cat = list(load_jsonl("catalog.jsonl").values())
    todo = [r["id"] for r in cat if not r.get("d") and not r.get("pr")]  # 発売日も価格もない＝発売予定で日付不明
    old = load_json("release_dates.json", {})
    out = {}
    for i in range(0, len(todo), 20):
        ids = todo[i:i + 20]
        try:
            j = json.loads(http(DC.format(ids=",".join(ids)), tries=2))
        except Exception as e:
            print("取得に失敗", e)
            out.update({k: old[k] for k in ids if k in old})
            continue
        for p in j.get("Products") or []:
            ds = []
            for m in p.get("MarketProperties") or []:
                ds.append(jst_date(m.get("OriginalReleaseDate") or ""))
            for a in p.get("DisplaySkuAvailabilities") or []:
                for av in a.get("Availabilities") or []:
                    ds.append(jst_date((av.get("Properties") or {}).get("PreOrderReleaseDate") or ""))
            ds = sorted(x for x in ds if x)
            if ds:
                out[p["ProductId"]] = ds[0]
        time.sleep(0.5)
    save_json("release_dates.json", dict(sorted(out.items())))
    print("発売日を補った作品", len(out), "/", len(todo))


if __name__ == "__main__":
    main()
