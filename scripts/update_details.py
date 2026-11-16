"""各作品のストアページを1本ずつ読み、日本語の対応状況・Play Anywhere・説明文を取得する。
まだ取得していない作品を、発売予定・最近の作品から優先して進める。決めた時間が来たら止まり、続きは次回。"""
import argparse, time, urllib.error
from common import *

ap = argparse.ArgumentParser()
ap.add_argument("--minutes", type=float, default=50)
args = ap.parse_args()

cat = load_jsonl("catalog.jsonl")
det = load_jsonl("details.jsonl")
T = today()
recent = today(-60)
week_ago = today(-7)

# 取得する順番: 未取得（発売予定・直近60日→新しい順）→ 発売前後の作品の取り直し（週1回）
missing = [i for i in cat if i not in det]
first = [i for i in missing if (cat[i].get("d") or "9999") >= recent]
rest = sorted((i for i in missing if (cat[i].get("d") or "9999") < recent), key=lambda i: cat[i].get("d") or "", reverse=True)
refresh = [i for i, r in det.items() if i in cat and (cat[i].get("d") or "9999") >= today(-14) and r.get("at", "") <= week_ago]
queue = first + rest + refresh
print(f"details: {len(det)} done, {len(missing)} missing, {len(refresh)} to refresh", flush=True)

end = time.time() + args.minutes * 60
n = 0
for gid in queue:
    if time.time() > end:
        break
    try:
        html = http(STORE.format(loc="ja-JP", id=gid)).decode("utf-8", "replace")
        st = preloaded(html)
        p = ((st or {}).get("core2", {}).get("products", {}).get("productSummaries", {}) or {}).get(gid)
    except urllib.error.HTTPError:
        p = None
    except RuntimeError as e:
        print(" ", e, flush=True)
        continue
    if not p:
        det[gid] = {"id": gid, "none": 1, "at": T}
    else:
        L = p.get("languagesSupported") or {}
        ja = L.get("ja-JP")
        lang = None if not L else ([int(bool(ja.get("isAudioSupported"))), int(bool(ja.get("isInterfaceSupported"))),
                                    int(bool(ja.get("areSubtitlesSupported")))] if ja else [0, 0, 0])
        rec = {"id": gid, "lang": lang, "pa": int("XPA" in (p.get("capabilities") or {})),
               "desc": " ".join((p.get("description") or "").split())[:200], "at": T}
        rd = (p.get("releaseDate") or "")[:10]
        if rd and rd < "9000":
            rec["d"] = rd
        det[gid] = rec
    n += 1
    if n % 200 == 0:
        save_jsonl("details.jsonl", det)
        print(f"  {n} fetched", flush=True)
    time.sleep(1)

save_jsonl("details.jsonl", det)
left = sum(1 for i in cat if i not in det)
print(f"fetched {n}; {left} still missing", flush=True)
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"left={left}\n")
