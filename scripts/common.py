"""ハコサーチの取得・生成スクリプト共通部分。ストアに負荷をかけないよう、通信は1秒以上の間隔で行う。"""
import base64, datetime, json, os, time, urllib.error, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
BROWSE = "https://emerald.xboxservices.com/xboxcomfd/browse?locale={loc}"
STORE = "https://www.xbox.com/{loc}/games/store/_/{id}"
IMG_PREFIX = "https://store-images.s-microsoft.com/image/apps."
# ストア内部のサブスクID → 表示名（表示順もこの順）
PASS = {
    "CFQ7TTC0K5DJ": "Essential",
    "CFQ7TTC0P85B": "Premium",
    "CFQ7TTC0KHS0": "Ultimate",
    "CFQ7TTC0KGQ8": "PC Game Pass",
    "CFQ7TTC0K5DH": "EA Play",
    "CFQ7TTC0QH5H": "Ubisoft+",
}
ORDER = list(PASS.values())
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def today(days=0):
    """日本時間の今日（days日ずらせる）を YYYY-MM-DD で返す"""
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9, days=days)
    return now.date().isoformat()


def http(url, data=None, headers=None, tries=5):
    h = {"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"}
    h.update(headers or {})
    for i in range(tries):
        wait = 10 * (i + 1)
        try:
            req = urllib.request.Request(url, data=data, headers=h, method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            ra = e.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = max(wait, int(ra))
            print(f"  HTTP {e.code} {url[:90]} -> retry in {wait}s", flush=True)
        except Exception as e:  # 通信エラー
            print(f"  {type(e).__name__} {url[:90]} -> retry in {wait}s", flush=True)
        time.sleep(wait)
    raise RuntimeError("failed: " + url)


def browse(filters=None, loc="ja-JP", sort="ReleaseDate desc", tag="hakosearch"):
    """ストアの一覧APIを最後までページ送りし、1ページごとに (作品リスト, チャンネル) を返す"""
    f = {"orderby": {"id": "orderby", "choices": [{"id": sort}]}}
    f.update(filters or {})
    fb = base64.b64encode(json.dumps(f).encode()).decode()
    ct, n = "", 0
    while True:
        n += 1
        body = json.dumps({"Filters": fb, "ReturnFilters": False, "ChannelKeyToBeUsedInResponse": "K",
                           "EncodedCT": ct, "ChannelId": ""}).encode()
        j = json.loads(http(BROWSE.format(loc=loc), body,
                            {"content-type": "application/json", "x-ms-api-version": "1.1", "ms-cv": f"{tag}.{n}"}))
        ch = list(j["channels"].values())[0]
        yield j.get("productSummaries") or [], ch
        ct = ch.get("encodedCT")
        more = False
        if ct:
            try:
                more = json.loads(base64.b64decode(ct)).get("HasMore", False)
            except Exception:
                more = True
        time.sleep(1)
        if not more:
            return


SEARCH = "https://emerald.xboxservices.com/xboxcomfd/search/games?locale={loc}"


def search(query, loc="ja-JP", tag="hakodigSearch", max_pages=60):
    """ストアの検索APIを最後までページ送りし、1ページごとに作品リストを返す"""
    ct, n = "", 0
    while n < max_pages:
        n += 1
        body = json.dumps({"Query": query, "Filters": "", "ReturnFilters": False,
                           "ChannelKeyToBeUsedInResponse": "S", "EncodedCT": ct}).encode()
        j = json.loads(http(SEARCH.format(loc=loc), body,
                            {"content-type": "application/json", "x-ms-api-version": "1.1", "ms-cv": f"{tag}.{n}"}))
        ch = list((j.get("channels") or {"x": {}}).values())[0]
        yield j.get("productSummaries") or []
        ct = ch.get("encodedCT")
        more = False
        if ct:
            try:
                more = json.loads(base64.b64decode(ct)).get("HasMore", False)
            except Exception:
                more = True
        time.sleep(1)
        if not more:
            return


def browse_ids(filters, tag):
    ids = set()
    for ps, ch in browse(filters, tag=tag):
        ids.update(p["productId"] for p in ch.get("products") or [])
    return ids


def preloaded(html):
    """ストアページに埋め込まれた __PRELOADED_STATE__ を取り出す"""
    i = html.find("window.__PRELOADED_STATE__ = ")
    if i < 0:
        return None
    st = html.find("{", i)
    depth, ins, esc = 0, False, False
    for j in range(st, len(html)):
        c = html[j]
        if ins:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                ins = False
            continue
        if c == '"':
            ins = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[st:j + 1])
    return None


def load_jsonl(name):
    d, p = {}, os.path.join(DATA, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    d[r["id"]] = r
    return d


def save_jsonl(name, d):
    """1作品1行・ID順で保存（毎日の差分が小さくなるように）"""
    p = os.path.join(DATA, name)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        for k in sorted(d):
            f.write(json.dumps(d[k], ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(p + ".tmp", p)


def load_json(name, default):
    p = os.path.join(DATA, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def sale_end(s):
    """ストアのセール終了日時（UTC, 例 "11/17/2026 23:59:59"）を日本時間の日付 "MM/DD/YYYY" にする。期限なし（9998年）は空"""
    if not s or s.startswith("12/30/9998"):
        return ""
    try:
        return (datetime.datetime.strptime(s, "%m/%d/%Y %H:%M:%S") + datetime.timedelta(hours=9)).strftime("%m/%d/%Y")
    except ValueError:
        return s.split(" ")[0]
