"""DLC（アドオン）の一覧を取る。
対象: 格闘ゲーム（ジャンルに「格闘」を含む作品。体験版は除く）＋ data/dlc_targets.json で手動指定した作品。
朝の回は対象を全部、夕方の回（--evening）はDLCがあると分かっている作品だけ取り直す（セール価格の反映用）。
ストアの「この作品のアドオン」の一覧を1秒間隔で順番に取り、data/dlc.json に保存する。"""
import argparse, json, re, time
from common import *

ap = argparse.ArgumentParser()
ap.add_argument("--evening", action="store_true")
args = ap.parse_args()

cat = load_jsonl("catalog.jsonl")
old = load_json("dlc.json", {})
DEMO = re.compile(r"体験版|デモ版|トライアル版|\bdemo\b|\bfree trial\b", re.I)
targets = [i for i, r in cat.items() if "格闘" in (r.get("cat") or "") and not DEMO.search(r["t"])]
targets += [i for i in load_json("dlc_targets.json", []) if i in cat and i not in targets]
if args.evening:
    targets = [i for i in targets if i in old]

NAME_IN = re.compile(r"[「\"“]([^」\"”]{1,30})[」\"”]")
def contents(desc):
    """シーズンパスなどの説明文の「・〜」の行から、含まれるキャラ等の名前を拾う"""
    names = []
    for line in (desc or "").splitlines():
        if line.strip().startswith(("・", "-", "•")):
            names += [n for n in NAME_IN.findall(line) if n not in ("追加ステージ", "ゲーム本編")]
    return names

def addons(gid, sub):
    ct, n, items = "", 0, []
    while n < 80:  # 1ページ25件。DOAシリーズのようにコスチュームが千件を超える作品もある
        n += 1
        body = json.dumps({"Filters": "", "ReturnFilters": False, "ChannelKeyToBeUsedInResponse": "A",
                           "EncodedCT": ct, "ChannelId": "PRODUCTADDONS_" + gid}).encode()
        j = json.loads(http(BROWSE.format(loc="ja-JP"), body,
                            {"content-type": "application/json", "x-ms-api-version": "1.1", "ms-cv": f"hakodigDlc.{n}"}))
        ps = j.get("productSummaries") or []
        for p in ps:
            pr = ((p.get("specificPrices") or {}).get("purchaseable") or [{}])[0]
            off = round(pr.get("discountPercentage") or 0)
            end = sale_end(pr.get("endDateUtc") or "") if off else ""  # 日本時間の日付
            items.append([p["productId"], p.get("title") or "", pr.get("listPrice"), pr.get("msrp"), off, end])
            c = contents(p.get("description"))
            if c:
                sub[p["productId"]] = c  # このDLC（シーズンパス等）に含まれるもの
        ch = list((j.get("channels") or {"x": {}}).values())[0]
        ct = ch.get("encodedCT")
        time.sleep(1)
        more = False
        if ct and ps:
            try:
                more = json.loads(base64.b64decode(ct)).get("HasMore", False)
            except Exception:
                more = True
        if not more:
            return items
    return items

def bundled(gid):
    """このエディションに同梱されているもの（本編・シーズンパスなど）のID"""
    body = json.dumps({"Filters": "", "ReturnFilters": False, "ChannelKeyToBeUsedInResponse": "B",
                       "EncodedCT": "", "ChannelId": "INTHISBUNDLE_" + gid}).encode()
    j = json.loads(http(BROWSE.format(loc="ja-JP"), body,
                        {"content-type": "application/json", "x-ms-api-version": "1.1", "ms-cv": "hakodigBundle.1"}))
    time.sleep(1)
    return [p["productId"] for p in j.get("productSummaries") or []]

BUNDLE_CACHE = {}
def bundled_all(gid):
    """同梱されているものに加えて、同梱のシーズンパスなどに含まれる中身（キャラ等）も返す"""
    inc = bundled(gid)
    out = list(inc)
    for i in inc:
        if i == gid:
            continue
        if i not in BUNDLE_CACHE:
            try:
                BUNDLE_CACHE[i] = bundled(i)
            except Exception:
                BUNDLE_CACHE[i] = []
        out += [x for x in BUNDLE_CACHE[i] if x not in out]
    return out

T = today()
out = dict(old)
ok = 0
for gid in targets:
    try:
        sub = {}
        items = addons(gid, sub)
    except Exception as e:
        print("dlc failed:", gid, e, flush=True)
        continue
    ok += 1
    if items:
        try:
            inc = bundled_all(gid)
        except Exception:
            inc = (old.get(gid) or {}).get("inc", [])
        out[gid] = {"at": T, "items": items, "inc": inc, "sub": sub}
    else:
        out.pop(gid, None)
# 対象から外れた作品（ストアから消えた等）は消す
keep = set(i for i, r in cat.items() if "格闘" in (r.get("cat") or "")) | set(load_json("dlc_targets.json", []))
out = {k: v for k, v in out.items() if k in keep}
save_json("dlc.json", dict(sorted(out.items())))
print(f"dlc: checked {ok}/{len(targets)}, games with DLC {len(out)}, items {sum(len(v['items']) for v in out.values())}", flush=True)
