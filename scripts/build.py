import unicodedata
import re
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
man_dates = overrides.get("dates", {})  # 発売日の手動指定
meta = load_json("meta.json", {})
T = today()
NOW_HM = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%H:%M")
# Xboxアプリと同じデータベースから補った発売日（update_dates.py）。これからの日付だけ使う
# （過去の日付は、販売が止まった作品を「発売中」に移してしまうおそれがあるので使わない）
APP_WAIT = today(-30)  # アプリ側の日付を過ぎても、ストアに発売日が入るまで発売予定にしておく期間
rel_dates = {k: v for k, v in load_json("release_dates.json", {}).items() if v >= APP_WAIT}

# ---------- 英語タイトルのカタカナ読み ----------
# data/kana_words.txt（手で足した単語）→ alkana（英単語辞書）の順に引く。読めない単語は飛ばす
KANA_WORDS = {}
for line in open(os.path.join(ROOT, "data", "kana_words.txt"), encoding="utf-8"):
    if "=" in line and not line.startswith("#"):
        w, k = line.strip().split("=", 1)
        KANA_WORDS[w.lower()] = k
try:
    import alkana
except ImportError:
    alkana = None
SKIP_WORDS = set("ii iii iv vi vii viii ix xi xii xiii xiv xv xvi hd dlc ea th dx vs io fi op td ai sc gp fx alt tcg fc rpg x fmv wwii nba nfl nhl mlb pga ufc wwe fia wrc mx gat jdm mxgp motogp the a an and".split())
def word_kana(w):
    if w in KANA_WORDS:
        return KANA_WORDS[w]
    if not alkana:
        return None
    k = alkana.get_kana(w)
    if k:
        return k
    for suf in ("'s", "es", "s"):
        if w.endswith(suf) and len(w) > 3:
            k = KANA_WORDS.get(w[:-len(suf)]) or alkana.get_kana(w[:-len(suf)])
            if k:
                return k + "ズ"
    return None
def kana_reading(title):
    words = re.findall(r"[A-Za-z][A-Za-z']+", re.sub(r"[®™©]", "", title))
    out = []
    for w in words:
        w = w.lower().strip("'")
        if w in SKIP_WORDS:
            continue
        k = word_kana(w)
        if k:
            out.append(k)
    return " ".join(out) or None

# ---------- 英語タイトルの作品の日本名 ----------
# data/ja_names.json（手で足したもの）と、ストアの説明文の書き出し「『〇〇』は…」から拾う
JA_NAMES = {k.lower(): v for k, v in load_json("ja_names.json", {}).items() if not k.startswith("_")}
JP_CHARS = re.compile(r"[ぁ-んァ-ヶ一-龯]")
def ja_name(title, desc):
    if JP_CHARS.search(title):
        return None
    names = [n for k, v in JA_NAMES.items() if k in title.lower() for n in v]
    m = re.match(r"\s*[『「]([^』」]{2,30})[』」]", desc)
    if m:
        n = m.group(1).strip()
        # 文章の一部らしいもの（助詞を含む）や「〜版」は除く
        if JP_CHARS.search(n) and not re.search(r"[をにがへ]|ている|版$", n):
            names.append(n)
    return " ".join(dict.fromkeys(names)) or None

DEMO = re.compile(r"体験版|デモ版|トライアル版|\bdemo\b|\bfree trial\b", re.I)

sale_start = load_json("sale_start.json", {})
first_seen = load_json("first_seen.json", {})  # ハコディグに初めて載った日時（最近14日分）
dlc = load_json("dlc.json", {})
GP_MANUAL = load_json("gp_manual.json", {})
# 同梱されているDLC（シーズンパスなど）は、そのエディションの一覧から除く
for v in dlc.values():
    inc = set(v.get("inc") or [])
    # 同梱のシーズンパスなどに含まれるキャラ等も除く（DLC名に「"春麗"」「「ケン」」のように名前が入っているもの）
    nf = lambda x: unicodedata.normalize("NFKC", x).lower().replace(" ", "")
    names = [nf(n) for i in inc for n in (v.get("sub") or {}).get(i, [])]
    quoted = lambda t: any(q[0] + n + q[1] in nf(t) for n in names for q in ('""', "「」", "“”"))
    v["items"] = [x for x in v["items"] if x[0] not in inc and not quoted(x[1])]

games, desc = [], {}
for gid, r in cat.items():
    if gid in force_hide:
        continue
    dt = det.get(gid, {})
    g = {"id": gid, "t": r["t"], "pub": r.get("pub", ""), "cat": r.get("cat", ""),
         "d": next((x for x in (r.get("d"), dt.get("d"), rel_dates.get(gid), man_dates.get(gid)) if x and x < "2100"), None), "pl": r.get("pl", []), "gp": r.get("gp", []),
         "pr": r.get("pr") or dt.get("pr"),  # 一覧に価格がまだないときはストアページの価格
         "img": r.get("img")}
    # 発売中かどうかの判定に使うのは「ストアの発売日時」だけ。アプリ側（release_dates）や手動の発売日は表示用
    if any(x and x < "2100" for x in (r.get("d"), dt.get("d"))):
        g["sd"] = 1  # 発売日はストアの情報
        rt = r.get("rt") if r.get("d") else dt.get("rt")  # ストアの発売時刻（日本時間）
        if rt:
            g["rt"] = rt  # 発売時刻（日本時間）。この時刻を過ぎるまでは発売中にしない
    if gid in dlc and dlc[gid]["items"]:
        g["dl"] = len(dlc[gid]["items"])  # DLCの数（中身はカードで押したときに dlc/ID.json を読む）
    if r.get("ge") and r.get("gp"):
        g["ge"] = r["ge"]  # ゲームパスなどに入った日
    if gid in sale_start and r.get("pr") and r["pr"][2]:
        g["ss"] = sale_start[gid]  # セールの開始日（ハコディグが見つけた日）
    if gid in first_seen:
        g["fs"] = first_seen[gid]
    if r.get("e"):
        g["e"] = r["e"]
    if DEMO.search(r["t"]):
        g["dm"] = 1  # 体験版
    j = ja_name(r["t"], dt.get("desc") or "")
    if j:
        g["j"] = j  # 日本での名前（「井戸の烏」など）
    k = kana_reading(r["t"])
    if k:
        g["k"] = k  # 英語タイトルのカタカナ読み（「ギアーズ」「ヘイロー」などで探せるように）
    # ゲームパスの終了予定日（60日以内のものだけ。9998年などの仮の日付や遠い契約期限は除く）
    gx = {k: v for k, v in (r.get("gx") or {}).items() if T <= v <= today(60)}
    # Xbox Wire などで発表された終了日（ストアに日付が入るまでの手動の補足）
    if gid in GP_MANUAL.get("leave", {}):
        for k in r.get("gp") or []:
            if k in ("Essential", "Premium", "Ultimate", "PC Game Pass") and T <= GP_MANUAL["leave"][gid]:
                gx.setdefault(k, GP_MANUAL["leave"][gid])
    for k in r.get("lv") or []:  # ゲームパスの「まもなく終了」一覧に載っている（終了日は未発表）
        gx.setdefault(k, "soon")
    if gx:
        g["gx"] = gx
    gn = {k: v for k, v in (r.get("gn") or {}).items() if T < v <= today(60)}
    for k, d in (GP_MANUAL.get("add", {}).get(gid) or {}).items():  # 発表済みでストアに未反映の追加予定
        if T < d and k not in (r.get("gp") or []):
            gn.setdefault(k, d)
    if gn:
        g["gn"] = gn  # ゲームパスに近日追加
    if r.get("rc"):
        g["rc"] = 1  # ストアに評価がある（発売済みの目印）
    if gid in force_rel:
        g["rs"] = 1  # 手動で発売済みに指定
    elif not g.get("sd") and gid in low:
        g["rs"] = 1  # 一度でも価格が付いた作品は発売済み（販売終了で価格が消えても発売予定に戻さない）
    if dt.get("np"):
        g["np"] = 1  # ストアページに単品の販売がない
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
# src/template.html の released1 と同じ式（CLAUDE.md「発売中・発売予定の分け方」の 1→2→3 の順）。
# 画面の発売中・発売予定はページを開いた時点で決まる。ここ（サイトを作った時点）の結果は、予約版を隠す・別エディションの目印に使うだけ
def is_released(g):
    if g.get("sd"):  # ストアに発売日がある → その日時（日本時間）を過ぎ、価格（無料を含む）かゲームパスがあれば発売中
        due = g["d"] < T or (g["d"] == T and (g.get("rt") or "00:00") <= NOW_HM)
        return due and (g["d"] < APP_WAIT or g.get("pr") is not None or bool(g["gp"]))  # 最近の作品は価格が入るまで発売予定
    if g["d"] and g["d"] >= APP_WAIT:  # ストアに日付がなく、アプリ・手動の日付がある（過ぎて30日以内も）→ ストアに日付が入るまで発売予定
        return False
    # ストアに日付がない作品（古い作品・販売終了など）は、発売済みの目印があれば発売中
    return bool(g["gp"] or g.get("rc") or (g.get("pr") and g["pr"][0]) or PREVIEW.search(g["t"])
                or not g["id"].startswith("9") or "XCloud" in g["pl"] or g.get("big") or g.get("rs"))
rel_titles = sorted({nt(g["t"]) for g in games if is_released(g)}, key=len, reverse=True)
rel_set = set(rel_titles)
sib, hidden, keep, husk = 0, 0, [], []
for g in games:
    t = nt(g["t"])
    # サウンドトラック・アートブックだけの商品は表示しない（ゲーム付きのエディションは残す）
    if SOUND.search(t) and not WITHGAME.search(t):
        hidden += 1
        continue
    # ストアの残骸：発売日が先の作品を除き（日付がない・過ぎた）、ストアページに自分の販売がなく（ほかの商品の販売だけ）価格もゲームパスもない（デラックス版の中身・販売の終わったセット版など）は表示しない
    if g.get("np") and not (g["d"] and g["d"] >= T) and g.get("pr") is None and not g["gp"]:
        hidden += 1
        husk.append(g["t"])
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
print("hidden (pre-orders, soundtracks, store husks):", hidden, "husks:", husk)
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

# 大型セール：名前つき（data/big_sales.json）＋同じ終了日が400本以上のまとまり
from collections import Counter
ends = Counter(g["pr"][3] for g in games if g.get("pr") and g["pr"][2] and g["pr"][3] and not g.get("dm"))
big_ids = load_json("big_sale_ids.json", {})
def in_big(g, b):  # 公式ページ（channel）に載っている作品。channel がなければ終了日と開始日で選ぶ
    if not (g.get("pr") and g["pr"][2] and not g.get("dm")):
        return False
    ss = (g.get("ss") or "0000")[:10]  # 日付だけで比べる（後ろの b, c… は同じ日の何回目の更新か）
    if not (b.get("since", "0000") <= ss <= b.get("until", "9999")):
        return False
    if b.get("channel"):
        return g["id"] in chset.get(b["channel"], set())
    return g["pr"][3] in b["ends"]
chset = {k: set(v) for k, v in big_ids.items()}
big, used, bigout = [], set(), {}
for b in load_json("big_sales.json", {}).get("sales", []):
    hit = [g["id"] for g in games if in_big(g, b)]
    if len(hit) >= 50:
        e = {"n": b["name"], "e": b["ends"], **{k: b[x] for k, x in (("p", "period"), ("f", "from"), ("s", "since"), ("u", "until")) if b.get(x)}}
        if b.get("channel"):
            e["c"] = b["channel"]; bigout[b["channel"]] = sorted(set(bigout.get(b["channel"], [])) | set(hit))  # ページを開いたときに bigsale.json を1回だけ読む
        big.append(e); used.update(b["ends"])
with open(os.path.join(OUT, "bigsale.json"), "w", encoding="utf-8") as f:
    f.write(dump(bigout))  # 大型セールの公式ページに載っている作品ID（ページを開いたときに1回だけ読む）
# 今週のセール：その週（火曜〜翌週月曜）に始まったセール。週替わりセールは火曜に始まり、水・木曜にも追加がある。
# ほかのボタン（大型セール）に入っている作品は入れない。50本以上あればボタンを出す
WEEKLY_FROM = "2026-11-24"
today_d = datetime.date.fromisoformat(T)
wk = today_d - datetime.timedelta(days=(today_d.weekday() - 1) % 7)  # 直近の火曜
if str(wk) >= WEEKLY_FROM:
    named = [b for b in load_json("big_sales.json", {}).get("sales", []) if any(x["n"] == b["name"] for x in big)]
    ex = {g["id"] for g in games for b in named if in_big(g, b)}
    wb = {"ends": None, "since": str(wk), "until": str(wk + datetime.timedelta(days=6))}
    hit = [g for g in games if g.get("pr") and g["pr"][2] and not g.get("dm") and g["id"] not in ex
           and wb["since"] <= (g.get("ss") or "0000")[:10] <= wb["until"]]
    if len(hit) >= 50:
        big.append({"n": "今週のセール", "tag": "", "w": 1, "s": wb["since"], "u": wb["until"],
                    "e": [], "p": f"{wk.month}/{wk.day}〜"})
for e, n in ends.most_common():
    if n >= 400 and e not in used:
        big.append({"n": f"{int(e[:2])}/{int(e[3:5])}までの大型セール", "e": [e]})

t = open(os.path.join(ROOT, "src", "template.html"), encoding="utf-8").read()
t = (t.replace("__DATA__", dump(first)).replace("__ALIASES__", dump(aliases)).replace("__PUBS__", dump(load_json("publishers.json", [])))
      .replace("__UPDATES__", json.dumps(load_json("changelog.json", [])[:10], ensure_ascii=False, separators=(",", ":"))).replace("__FETCHED__", (meta.get("list_at") or T).replace("-", ".") + (" " + meta["list_t"] if meta.get("list_t") else "")).replace("__TODAY__", T).replace("__APP_WAIT__", APP_WAIT).replace("__BIG__", dump(big)))
page = ('<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="description" content="Xbox日本ストアのゲームを、日本語対応・ゲームパス・価格で探せる非公式の検索サポート。by ハコイチバ">\n'
        '<style>html,body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
        '</head>\n<body>\n' + t + '\n</body>\n</html>\n')
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(page)
open(os.path.join(OUT, ".nojekyll"), "w").close()

# DLC一覧（作品ごと。カードで「DLC」を押したときだけ読む）
os.makedirs(os.path.join(OUT, "dlc"), exist_ok=True)
for gid, v in dlc.items():
    with open(os.path.join(OUT, "dlc", gid + ".json"), "w", encoding="utf-8") as f:
        json.dump(v["items"], f, ensure_ascii=False, separators=(",", ":"))

# プライバシーポリシー・利用規約
head = open(os.path.join(ROOT, "src", "pages", "_head.html"), encoding="utf-8").read()
for name, title in [("privacy", "プライバシーポリシー"), ("terms", "利用規約")]:
    body = open(os.path.join(ROOT, "src", "pages", name + ".html"), encoding="utf-8").read()
    with open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8") as f:
        f.write(head.replace("__TITLE__", title) + body)

# 画像などの素材（背景画像）をそのままコピー
if os.path.isdir(os.path.join(ROOT, "src", "assets")):
    shutil.copytree(os.path.join(ROOT, "src", "assets"), os.path.join(OUT, "assets"))
for f in os.listdir(os.path.join(ROOT, "src", "static")):  # favicon.ico・apple-touch-icon.png・robots.txt（ブラウザが自動で探すもの）
    shutil.copy(os.path.join(ROOT, "src", "static", f), os.path.join(OUT, f))

# 安全のためのヘッダー。ページ内のプログラムは、このページに書いたもの（ハッシュで指定）以外は動かさない
import hashlib, base64
sh = lambda x: "'sha256-" + base64.b64encode(hashlib.sha256(x.encode()).digest()).decode() + "'"
scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
csp = "; ".join([
    "default-src 'self'",
    "script-src " + " ".join(sh(x) for x in scripts),
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data: https://store-images.s-microsoft.com",
    "connect-src 'self'",
    "base-uri 'none'", "form-action 'self'", "frame-ancestors 'none'", "object-src 'none'",
])
with open(os.path.join(OUT, "_headers"), "w") as f:
    f.write("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
            "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()\n"
            "  Strict-Transport-Security: max-age=31536000\n  Content-Security-Policy: " + csp + "\n"
            + "/assets/*\n  Cache-Control: public, max-age=2592000\n")

done = sum(1 for g in games if "lp" not in g)
print(f"built: {len(games)} games, first {len(first)}, rest {len(rest)}, language info {done}/{len(games)}")
