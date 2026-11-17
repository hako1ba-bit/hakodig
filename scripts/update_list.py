"""毎日: ストアの一覧を取り直し、作品の基本情報・価格・サブスク・Play Anywhere を更新する。
週1回: 北米ストアのタイトル（英語名での検索用）も取り直す。"""
import re
from common import *

cat = load_jsonl("catalog.jsonl")
low = load_jsonl("low.jsonl")
meta = load_json("meta.json", {})
T = today()


def compact(p):
    ps = (p.get("specificPrices") or {}).get("purchaseable") or []
    pr = None
    if ps:
        b = min(ps, key=lambda c: c.get("listPrice", 0))
        end = b.get("endDateUtc") or ""
        end = end.split(" ")[0] if b.get("discountPercentage", 0) > 0 and not end.startswith("12/30/9998") else ""
        pr = [b.get("listPrice"), b.get("msrp"), round(b.get("discountPercentage", 0)), end]
    imgs = p.get("images") or {}
    img = (imgs.get("poster") or imgs.get("boxArt") or {}).get("url") or None
    if img and img.startswith(IMG_PREFIX):
        img = img[len(IMG_PREFIX):]
    d = (p.get("releaseDate") or "")[:10] or None
    if d and d >= "2100":  # 9998年・2799年などの仮の日付
        d = None
    # passMetadata には過去の参加履歴も残っている。外れた日（exitDateUTC）が過ぎたプランは除き、未来なら終了予定日として残す
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    gp, gx, gn = {PASS[k] for k in p.get("includedWithPassesProductIds") or [] if k in PASS}, {}, {}
    jst = lambda x: (datetime.datetime.fromisoformat(x.replace("Z", "+00:00")) + datetime.timedelta(hours=9)).date().isoformat()
    for k, m in (p.get("passMetadataByPassProductId") or {}).items():
        if k not in PASS:
            continue
        en = (m or {}).get("entryDateUTC") or ""
        if en > now:  # これから追加される（近日追加）
            gn[PASS[k]] = jst(en)
            gp.discard(PASS[k])
            continue
        ex = (m or {}).get("exitDateUTC") or ""
        if not ex:
            gp.add(PASS[k])
        elif ex > now:
            gp.add(PASS[k])
            gx[PASS[k]] = jst(ex)
    return {"id": p["productId"], "t": p.get("title") or "", "pub": (p.get("publisherName") or "").strip(),
            "cat": (p.get("categories") or [""])[0], "d": d, "pl": p.get("availableOn") or [],
            "gp": sorted(gp, key=ORDER.index), "pr": pr, "img": img, "rc": p.get("ratingCount") or 0, **({"gx": gx} if gx else {}), **({"gn": gn} if gn else {}),
            **({"big": 1} if (p.get("maxInstallSize") or 0) >= 1_000_000_000 else {})}


# 1. 全作品の一覧（発売日の新しい順）
fresh = {}
for ps, ch in browse(tag="hakosearchList"):
    for p in ps:
        fresh[p["productId"]] = compact(p)
print("list:", len(fresh), "/ store says", ch.get("totalItems"), flush=True)

# 1b. 体験版（一覧には載らないので、ストア検索で集める）
DEMO = re.compile(r"体験版|デモ版|トライアル版|\bdemo\b|\bfree trial\b", re.I)
nd = 0
for q in ("体験版", "demo", "デモ", "trial"):
    try:
        for ps in search(q, tag="hakodigDemo"):
            for p in ps:
                if DEMO.search(p.get("title") or "") and p["productId"] not in fresh:
                    fresh[p["productId"]] = compact(p); nd += 1
    except Exception as e:
        print("demo search failed:", q, e, flush=True)
print("demos added:", nd, flush=True)

# 2. サブスク（一覧の情報に含まれないものを補う）
for sid, name in PASS.items():
    ids = browse_ids({"IncludedInSubscription": {"id": "IncludedInSubscription", "choices": [{"id": sid}]}}, "hakosearchSub")
    for i in ids:
        if i in fresh and name not in fresh[i]["gp"]:
            fresh[i]["gp"] = sorted(fresh[i]["gp"] + [name], key=ORDER.index)
    print(f"sub {name}: {len(ids)}", flush=True)

# 3. Play Anywhere 対応
xpa = browse_ids({"PlayWith": {"id": "PlayWith", "choices": [{"id": "XboxPlayAnywhere"}]}}, "hakosearchXPA")
for i in xpa:
    if i in fresh:
        fresh[i]["xpa"] = 1
print("play anywhere:", len(xpa), flush=True)

# 4. 北米ストアのタイトル（7日に1回）
en_old = {k: v["e"] for k, v in cat.items() if v.get("e")}
if meta.get("en_at", "") <= today(-7):
    en = {}
    for ps, ch in browse(loc="en-US", tag="hakosearchEn"):
        for p in ps:
            en[p["productId"]] = p.get("title") or ""
    print("en-US titles:", len(en), flush=True)
    en_old = {i: t for i, t in en.items() if t}
    meta["en_at"] = T
for i, r in fresh.items():
    e = en_old.get(i)
    if e and e.strip().lower() != r["t"].strip().lower():
        r["e"] = e

# 5. 一覧から消えた作品は、14日続けて見つからなければ削除
partial = len(fresh) < 0.8 * len(cat)
for i, old in cat.items():
    if i in fresh:
        continue
    if partial:
        fresh[i] = old
        continue
    miss = old.get("miss", 0) + 1
    if miss <= 14:
        fresh[i] = dict(old, miss=miss)
for i, r in fresh.items():
    if i not in cat:
        r["new"] = T  # ハコサーチに登録された日
    elif cat[i].get("new"):
        r["new"] = cat[i]["new"]

# 6. 価格の記録（ハコサーチの記録上の最安値）
for i, r in fresh.items():
    pr = r.get("pr")
    if pr and pr[0] and pr[0] > 0 and (i not in low or pr[0] < low[i]["p"]):
        low[i] = {"id": i, "p": pr[0], "d": T}

save_jsonl("catalog.jsonl", fresh)
save_jsonl("low.jsonl", low)
meta["list_at"] = T
meta["list_t"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%H:%M")  # 日本時間
meta["count"] = len(fresh)
save_json("meta.json", meta)
print("saved catalog:", len(fresh), "partial" if partial else "", flush=True)
