"""発売日がWebストアのデータに入っていない「発売予定」の作品だけ、Xboxアプリと同じ商品データベース
（displaycatalog）から発売日を補う。結果は data/release_dates.json {作品ID: "YYYY-MM-DD"（日本時間）}。
build.py は、ストアのデータに発売日がないときだけこれを使う。"""
import datetime
import json
import time
from common import http, load_json, save_json, load_jsonl

DC = "https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={ids}&market=JP&languages=ja-jp"


def jst_date(s):
    """日本時間の "YYYY-MM-DD HH:MM"（並べ替えでいちばん早い日時を選べる）"""
    try:
        t = datetime.datetime.fromisoformat(s[:19]) + datetime.timedelta(hours=9)
    except ValueError:
        return None
    d = t.strftime("%Y-%m-%d %H:%M")
    return d if "2000" < d < "2100" else None  # 未定のときの仮の日付（2100年など）は使わない


def main():
    cat = list(load_jsonl("catalog.jsonl").values())
    todo = [r["id"] for r in cat if not r.get("d") and not r.get("pr")]  # 発売日も価格もない＝発売予定で日付不明
    old = load_json("release_dates.json", {})
    out = {}
    times = load_json("app_times.json", {})  # アプリ側の発売日時（日本時間）。ストアの発売日時と比べるために残しておく
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
                out[p["ProductId"]] = ds[0][:10]
                times[p["ProductId"]] = ds[0]
        time.sleep(0.5)
    save_json("release_dates.json", dict(sorted(out.items())))
    # アプリ側の日時と、あとからストアに入った日時を比べて記録する（CLAUDE.md「発売中・発売予定の分け方」）
    det = load_jsonl("details.jsonl")
    cmp = load_json("time_compare.json", {})
    by_id = {r["id"]: r for r in cat}
    for k, app in times.items():
        r, dt = by_id.get(k) or {}, det.get(k) or {}
        sd, srt = (r.get("d"), r.get("rt")) if r.get("d") else (dt.get("d"), dt.get("rt"))
        if sd and k not in cmp:
            store = f"{sd} {srt or '00:00'}"
            cmp[k] = {"t": r.get("t", ""), "app": app, "store": store, "same": app == store}
    save_json("app_times.json", dict(sorted(times.items())))
    save_json("time_compare.json", cmp)
    diff = [v for v in cmp.values() if not v["same"]]
    print("アプリとストアの発売日時の比較", len(cmp), "本、ずれ", len(diff), "本", *[f"{v['t']} アプリ{v['app']} ストア{v['store']}" for v in diff[-5:]], sep="\n  ")
    print("発売日を補った作品", len(out), "/", len(todo))


if __name__ == "__main__":
    main()
