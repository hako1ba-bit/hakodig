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
# 新しく載った・アプリの日付が近いのに、ストアの一覧に発売日も価格もない作品は、毎回ページを見に行く
# （一覧に日付がなくてもページには発売日時が入っていることがある。予告なしの配信を早く発売中にするため）
fs, app = load_json("first_seen.json", {}), load_json("release_dates.json", {})
watch = [i for i, r in cat.items() if not r.get("pr") and (
         (not r.get("d") and (i in fs or today(-30) <= (app.get(i) or "0") <= today(1)))
         or (r.get("d") and today(-30) <= r["d"] <= today(1)))]  # 発売日が近い・過ぎたばかりなのに価格がない作品も
# 全作品を少しずつ、確認日の古い順に確認し直す（アップデートで日本語が付いた作品などを拾う）
done_q = set(watch + first + rest + refresh)
rotate = sorted((i for i in det if i in cat and i not in done_q), key=lambda i: det[i].get("at", ""))[:args.rotate] if not missing else []
ws = set(watch)
queue = watch + [i for i in first + rest + refresh if i not in ws] + rotate
print(f"details: {len(det)} done, {len(watch)} dateless to watch, {len(missing)} missing, {len(refresh)} to refresh, {len(rotate)} to recheck", flush=True)

end = time.time() + args.minutes * 60
n = 0
new_pa = []  # 取り直しで、ストアページの記載が「Play Anywhere なし」→「あり」に変わった作品（＝本当に新しく対応した作品）
new_ja = []  # 取り直しで、日本語の音声・UI・字幕のどれかが新しく「対応」になった作品と、増えた項目
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
        # 一覧にまだ価格がない作品のために、ページの価格も残す（build.py は一覧に価格がないときだけ使う）
        prods = (st or {}).get("core2", {}).get("products", {}) or {}
        av = prods.get("availabilitySummaries")
        if av and not av.get(gid):
            rec["np"] = 1  # ページが別の商品の販売しか持っていない（デラックス版の中身・旧版の残骸など）。build.py で非表示
        for sku in ((prods.get("availabilitySummaries") or {}).get(gid) or {}).values():
            pz = [a.get("price") or {} for a in (sku or {}).values() if "Purchase" in (a.get("actions") or [])]
            pz = [x for x in pz if x.get("msrp") is not None]
            if pz:
                x = min(pz, key=lambda x: x.get("listPrice", x["msrp"]))
                rec["pr"] = [x.get("listPrice", x["msrp"]), x["msrp"], round(x.get("discountPercentage") or 0), ""]
                break
        d, rt = jst_release(p.get("releaseDate"))
        if d:
            rec["d"] = d
            if rt:
                rec["rt"] = rt
        old = det.get(gid) or {}
        if not old.get("none") and old.get("pa") == 0 and rec["pa"] == 1:
            new_pa.append(gid)
        # 前回「ストアページに記載なし」だった作品は数えない（ストア側で一時的に記載が消えることがあり、誤って「新しく対応」と出さないため）
        if old.get("lang") and rec["lang"] and not old.get("none"):
            before = old["lang"]
            added = [k for k, x, y in zip(("音声", "UI", "字幕"), before, rec["lang"]) if y and not x]
            if added:
                new_ja.append((gid, added))
        det[gid] = rec
    n += 1
    if n % 200 == 0:
        save_jsonl("details.jsonl", det)
        print(f"  {n} fetched", flush=True)
    time.sleep(1)

save_jsonl("details.jsonl", det)

# 「最新のアップデート」に、ストアページの記載が新しく変わった作品を記録（初回取得の作品は数えない）
def more(n):
    return f" ほか{n - 5}本" if n > 5 else ""

lines = []
if new_ja:  # 日本語対応がいちばん大事なので先に出す
    lines.append(f"日本語に対応した作品 {len(new_ja)}本：" + "、".join(f"{cat[i].get('t', i)}（{'・'.join(a)}）" for i, a in new_ja[:5]) + more(len(new_ja)))
if new_pa:
    lines.append(f"Play Anywhere 対応になった作品 {len(new_pa)}本：" + "、".join(cat[i].get("t", i) for i in new_pa[:5]) + more(len(new_pa)))
if lines:
    now = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
    log = load_json("changelog.json", [])
    for text in reversed(lines):  # 日本語対応の行が上に来るように
        log.insert(0, {"at": now, "text": text})
        print("changelog:", text, flush=True)
    save_json("changelog.json", log[:60])

left = sum(1 for i in cat if i not in det)
print(f"fetched {n}; {left} still missing", flush=True)
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"left={left}\n")
