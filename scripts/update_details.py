"""各作品のストアページを1本ずつ読み、日本語の対応状況・Play Anywhere・説明文を取得する。
まだ取得していない作品を、発売予定・最近の作品から優先して進める。決めた時間が来たら止まり、続きは次回。"""
import argparse, time, urllib.error
from common import *

ap = argparse.ArgumentParser()
ap.add_argument("--minutes", type=float, default=50)
ap.add_argument("--rotate", type=int, default=1500, help="古い順に確認し直す本数（1日あたり）")
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
# 全作品を少しずつ、確認日の古い順に確認し直す（アップデートで日本語が付いた作品などを拾う）
done_q = set(first + rest + refresh)
rotate = sorted((i for i in det if i in cat and i not in done_q), key=lambda i: det[i].get("at", ""))[:args.rotate] if not missing else []
queue = first + rest + refresh + rotate
print(f"details: {len(det)} done, {len(missing)} missing, {len(refresh)} to refresh, {len(rotate)} to recheck", flush=True)

end = time.time() + args.minutes * 60
n = 0
new_pa = []  # 取り直しで、ストアページの記載が「Play Anywhere なし」→「あり」に変わった作品（＝本当に新しく対応した作品）
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
        if rd and rd < "2100":
            rec["d"] = rd
        old = det.get(gid) or {}
        if not old.get("none") and old.get("pa") == 0 and rec["pa"] == 1:
            new_pa.append(gid)
        det[gid] = rec
    n += 1
    if n % 200 == 0:
        save_jsonl("details.jsonl", det)
        print(f"  {n} fetched", flush=True)
    time.sleep(1)

save_jsonl("details.jsonl", det)

# 「最新のアップデート」に、新しく Play Anywhere 対応になった作品を記録（初回取得の作品は数えない）
if new_pa:
    names = [cat[i].get("t", i) for i in new_pa]
    text = f"Play Anywhere 対応になった作品 {len(names)}本：" + "、".join(names[:5]) + (f" ほか{len(names) - 5}本" if len(names) > 5 else "")
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    log = load_json("changelog.json", [])
    log.insert(0, {"at": now.strftime("%Y-%m-%d %H:%M"), "text": text})
    save_json("changelog.json", log[:60])
    print("changelog:", text, flush=True)

left = sum(1 for i in cat if i not in det)
print(f"fetched {n}; {left} still missing", flush=True)
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"left={left}\n")
