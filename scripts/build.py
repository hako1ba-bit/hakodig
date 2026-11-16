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
meta = load_json("meta.json", {})
T = today()

games, desc = [], {}
for gid, r in cat.items():
    dt = det.get(gid, {})
    g = {"id": gid, "t": r["t"], "pub": r.get("pub", ""), "cat": r.get("cat", ""),
         "d": next((x for x in (r.get("d"), dt.get("d")) if x and x < "2100"), None), "pl": r.get("pl", []), "gp": r.get("gp", []),
         "pr": r.get("pr"), "img": r.get("img")}
    if r.get("e"):
        g["e"] = r["e"]
    if r.get("rc"):
        g["rc"] = 1  # ストアに評価がある（発売済みの目印）
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
