"""data/ の内容と src/template.html から、公開用のサイト一式を _site/ に作る。"""
import shutil
from common import *

ROOT = os.path.dirname(DATA)
OUT = os.path.join(ROOT, "_site")
LIM = 180

cat = load_jsonl("catalog.jsonl")
det = load_jsonl("details.jsonl")
low = load_jsonl("low.jsonl")
aliases = load_json("aliases.json", {})
overrides = load_json("overrides.json", {})
force_rel, force_hide = set(overrides.get("released", [])), set(overrides.get("hidden", []))
meta = load_json("meta.json", {})
T = today()

games, desc = [], {}
for gid, r in cat.items():
    if gid in force_hide:
        continue
    dt = det.get(gid, {})
    g = {"id": gid, "t": r["t"], "pub": r.get("pub", ""), "cat": r.get("cat", ""),
         "d": next((x for x in (r.get("d"), dt.get("d")) if x and x < "2100"), None), "pl": r.get("pl", []), "gp": r.get("gp", []),
         "pr": r.get("pr"), "img": r.get("img")}
    if r.get("e"):
        g["e"] = r["e"]
    # ゲームパスの終了予定日（60日以内のものだけ。9998年などの仮の日付や遠い契約期限は除く）
    gx = {k: v for k, v in (r.get("gx") or {}).items() if T <= v <= today(60)}
    if gx:
        g["gx"] = gx
    gn = {k: v for k, v in (r.get("gn") or {}).items() if T < v <= today(60)}
    if gn:
        g["gn"] = gn  # ゲームパスに近日追加
    if r.get("rc"):
        g["rc"] = 1  # ストアに評価がある（発売済みの目印）
    if gid in force_rel:
        g["rs"] = 1  # 手動で発売済みに指定
    elif not g["d"] and gid in low:
        g["rs"] = 1  # 一度でも価格が付いた作品は発売済み（販売終了で価格が消えても発売予定に戻さない）
    if r.get("big"):
        g["big"] = 1  # インストールサイズが1GB以上（中身が配信されている目印）
    if r.get("xpa") or dt.get("pa"):
        g["pa"] = 1
    if gid in det and not dt.get("none"):
        g["lang"] = dt.get("lang")
    else:
        g["lp"] = 1  # 言語情報 準備中
    lo, pr = low.get(gid), r.get("pr")
    if lo and pr and pr[0] and lo["p"] < pr[0]:
        g["lo"] = [lo["p"], lo["d"]]
    games.append(g)
    text = dt.get("desc") or ""
    if text:
        desc.setdefault(gid[-1], {})[gid] = text[:LIM] + ("…" if len(text) > LIM else "")

# 発売日の記載がない作品のうち、同じ発行元の発売済み作品の別エディション・別版は発売済みとみなす
import re
EDITION = re.compile(r"^\s*([-–—:：(（/]|edition|版|エディション|deluxe|gold|ultimate|complete|standard|premium|definitive|bundle|collection|デラックス|ゴールド|アルティメット|コンプリート|スタンダード|プレミアム|バンドル)", re.I)
nt = lambda x: re.sub(r"^windows store\s*-\s*", "", re.sub(r"[®™©]", "", x).replace("’", "'").replace("‘", "'").lower().strip())
SOUND = re.compile(r"soundtrack|サウンドトラック|\bost\b|artbook|アートブック", re.I)
WITHGAME = re.compile(r"edition|エディション|bundle|バンドル|版", re.I)
PRE = re.compile(r"\s*[-–(（]?\s*(pre-?order|予約(購入|特典)?版?)\s*[)）]?\s*$", re.I)
PREVIEW = re.compile(r"game preview|ゲーム ?プレビュー", re.I)
def is_released(g):  # src/template.html の released() と同じ判定
    if g["d"]:
        return g["d"] <= T
    return bool(g["gp"] or g.get("rc") or (g.get("pr") and g["pr"][0]) or PREVIEW.search(g["t"])
                or not g["id"].startswith("9") or "XCloud" in g["pl"] or g.get("big") or g.get("rs"))
rel_titles = sorted({nt(g["t"]) for g in games if is_released(g)}, key=len, reverse=True)
rel_set = set(rel_titles)
sib, hidden, keep = 0, 0, []
for g in games:
    t = nt(g["t"])
    # サウンドトラック・アートブックだけの商品は表示しない（ゲーム付きのエディションは残す）
    if SOUND.search(t) and not WITHGAME.search(t):
        hidden += 1
        continue
    # 予約版: 発売日を過ぎた、または本編が発売済みなら表示しない
    if PRE.search(t) and ((g["d"] and g["d"] <= T) or PRE.sub("", t).strip() in rel_set):
        hidden += 1
        continue
    keep.append(g)
    if is_released(g):
        continue
    for base in rel_titles:
        if len(base) >= 6 and t != base and t.startswith(base) and EDITION.match(t[len(base):]):
            g["rs"] = 1
            sib += 1
            break
games = keep
print("hidden (pre-orders, soundtracks):", hidden)
print("dateless editions of released games:", sib)

# 最初に読み込む分（直近2週間・発売予定）と、後から読み込む分に分ける
recent = today(-14)
first = [g for g in games if not g["d"] or g["d"] >= recent]
rest = [g for g in games if g["d"] and g["d"] < recent]

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(os.path.join(OUT, "d"))
dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
with open(os.path.join(OUT, "all.json"), "w", encoding="utf-8") as f:
    f.write(dump(rest))
for s, m in desc.items():
    with open(os.path.join(OUT, "d", s + ".json"), "w", encoding="utf-8") as f:
        f.write(dump(m))

t = open(os.path.join(ROOT, "src", "template.html"), encoding="utf-8").read()
t = (t.replace("__DATA__", dump(first)).replace("__ALIASES__", dump(aliases))
      .replace("__FETCHED__", T.replace("-", ".")).replace("__TODAY__", T))
page = ('<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="description" content="Xbox日本ストアのゲームを、日本語対応・ゲームパス・価格で探せる非公式の検索サポート。by ハコイチバ">\n'
        '<style>html,body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
        '</head>\n<body>\n' + t + '\n</body>\n</html>\n')
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(page)
open(os.path.join(OUT, ".nojekyll"), "w").close()

done = sum(1 for g in games if "lp" not in g)
print(f"built: {len(games)} games, first {len(first)}, rest {len(rest)}, language info {done}/{len(games)}")
