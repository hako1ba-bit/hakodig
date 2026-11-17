// ハコディグのログイン・コメント・お気に入り用API。サイト本体（_site）は静的ファイルとしてそのまま配信される。
//
// 安全のための決まりごと
// - ログインは Google。openid だけを求め、メールアドレス・名前・写真は受け取らない。
// - Google から届くアカウントID（sub）は、秘密の値（SUB_PEPPER）でハッシュ化してから保存する（元のIDは残さない）。
// - ログイン状態は HttpOnly・Secure・SameSite=Lax のクッキー。ページのプログラムからは読めない。
// - 書き込み系のAPIは、このサイト自身から来たリクエスト（Origin が一致）だけを受け付ける。
// - IPアドレスは保存しない。

const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const SESSION_DAYS = 30;
const NICK_MAX = 20;
const BODY_MAX = 140;
const enc = new TextEncoder();
const LIMIT = 500; // お気に入り・非表示の上限（1人あたり）
// 運営と紛らわしいニックネームは使えない（運営者本人は除く）
const RESERVED = ["ハコイチバ", "ハコディグ", "hakoichiba", "hakodig", "ナヴェ", "運営", "管理者", "管理人", "公式", "admin", "staff", "スタッフ", "モデレーター"];
const fold = x => x.normalize("NFKC").toLowerCase().replace(/[\u3041-\u3096]/g, c => String.fromCharCode(c.charCodeAt(0) + 0x60)).replace(/[\s\p{P}\p{S}ー]/gu, "");
const reserved = nick => RESERVED.some(r => fold(nick).includes(fold(r)));

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    try {
      if (p === "/auth/login") return login(req, env);
      if (p === "/auth/callback") return callback(req, env, url);
      if (p.startsWith("/api/")) return await api(req, env, url);
    } catch (e) {
      console.error(e && e.stack || e);
      return json({ error: "サーバーでエラーが起きました" }, 500);
    }
    return env.ASSETS.fetch(req);
  },
};

// ---------- 小道具 ----------
const now = () => new Date().toISOString();
const json = (o, status = 200, headers = {}) =>
  new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers } });
const b64url = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const rand = (n = 32) => b64url(crypto.getRandomValues(new Uint8Array(n)));
const sha256 = async s => b64url(await crypto.subtle.digest("SHA-256", enc.encode(s)));
async function hmac(key, s) {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", k, enc.encode(s)));
}
function cookies(req) {
  const out = {};
  for (const part of (req.headers.get("cookie") || "").split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i)] = part.slice(i + 1);
  }
  return out;
}
const setCookie = (name, value, maxAge) =>
  `${name}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
const redirect = (to, extra = []) => {
  const h = new Headers({ location: to, "cache-control": "no-store" });
  extra.forEach(c => h.append("set-cookie", c));
  return new Response(null, { status: 302, headers: h });
};
const ready = env => !!(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET && env.SUB_PEPPER);
const GAME_ID = /^[0-9A-Z]{12}$/;
// 文字数は見た目の1文字ずつ数える。改行は1つまで、制御文字は取り除く
function clean(s, max, lines = 3) {
  s = String(s || "").normalize("NFC").replace(/[\u0000-\u0009\u000B-\u001F\u007F​-‏‪-‮⁦-⁩]/g, "").trim();
  s = s.split("\n").map(x => x.trim()).filter((x, i, a) => x || (i > 0 && a[i - 1])).slice(0, lines).join("\n");
  return [...s].length > max ? null : s;
}

// ---------- ログイン ----------
async function login(req, env) {
  if (!ready(env)) return new Response("ログインは準備中です。", { status: 503, headers: { "content-type": "text/plain; charset=utf-8" } });
  const state = rand(), verifier = rand(48), nonce = rand();
  const q = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID, response_type: "code",
    redirect_uri: env.SITE + "/auth/callback", scope: "openid",
    state, nonce, code_challenge: await sha256(verifier), code_challenge_method: "S256", prompt: "select_account",
  });
  return redirect(`${AUTH_URL}?${q}`, [setCookie("__Host-hd_oauth", `${state}.${verifier}.${nonce}`, 600)]);
}

async function callback(req, env, url) {
  const clear = setCookie("__Host-hd_oauth", "", 0);
  const back = msg => redirect("/?login=" + msg, [clear]);
  if (!ready(env)) return back("unavailable");
  const [state, verifier, nonce] = (cookies(req)["__Host-hd_oauth"] || "").split(".");
  const code = url.searchParams.get("code");
  if (url.searchParams.get("error")) return back("cancel");
  if (!state || !code || url.searchParams.get("state") !== state) return back("error");

  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET, grant_type: "authorization_code",
      code, redirect_uri: env.SITE + "/auth/callback", code_verifier: verifier,
    }),
  });
  if (!res.ok) return back("error");
  const tok = await res.json();
  // IDトークンは Google から暗号化通信で直接受け取ったものなので、中身の確認だけ行う
  let claims;
  try { claims = JSON.parse(atob(tok.id_token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); } catch { return back("error"); }
  if (claims.aud !== env.GOOGLE_CLIENT_ID || claims.nonce !== nonce || !claims.sub || claims.exp * 1000 < Date.now()
      || !["https://accounts.google.com", "accounts.google.com"].includes(claims.iss)) return back("error");

  // 使うのは sub（アカウントID）だけ。ハッシュ化して保存し、それ以外の項目は保存しない
  const subHash = await hmac(env.SUB_PEPPER, claims.sub);
  let user = await env.DB.prepare("SELECT id, banned FROM users WHERE sub_hash = ?").bind(subHash).first();
  if (!user) {
    user = { id: rand(12), banned: 0 };
    await env.DB.prepare("INSERT INTO users (id, sub_hash, created_at) VALUES (?, ?, ?)").bind(user.id, subHash, now()).run();
  }
  if (user.banned) return back("banned");
  const token = rand();
  await env.DB.batch([
    env.DB.prepare("DELETE FROM sessions WHERE expires_at < ?").bind(Date.now()),
    env.DB.prepare("INSERT INTO sessions (hash, user_id, expires_at) VALUES (?, ?, ?)")
      .bind(await sha256(token), user.id, Date.now() + SESSION_DAYS * 864e5),
  ]);
  return redirect("/?login=ok", [clear, setCookie("__Host-hd_sid", token, SESSION_DAYS * 86400)]);
}

async function full(env, table, uid) {
  const r = await env.DB.prepare(`SELECT COUNT(*) AS n FROM ${table} WHERE user_id = ?`).bind(uid).first();
  return r && r.n >= LIMIT;
}

async function currentUser(req, env) {
  const token = cookies(req)["__Host-hd_sid"];
  if (!token) return null;
  const u = await env.DB.prepare(
    "SELECT u.id, u.nick, u.admin, u.banned FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.hash = ? AND s.expires_at > ?"
  ).bind(await sha256(token), Date.now()).first();
  return u && !u.banned ? u : null;
}

// ---------- API ----------
async function api(req, env, url) {
  const p = url.pathname, m = req.method;
  if (m !== "GET") {
    // よそのサイトから勝手に書き込ませる攻撃（CSRF）を防ぐ
    if (req.headers.get("origin") !== env.SITE) return json({ error: "不正なリクエストです" }, 403);
  }
  const body = m === "POST" ? await req.json().catch(() => ({})) : {};

  if (p === "/api/health") return json({ ok: true, login: ready(env) });

  // コメント一覧はログインしていなくても見られる
  if (p === "/api/comments" && m === "GET") {
    const g = url.searchParams.get("g") || "";
    if (!GAME_ID.test(g)) return json({ error: "作品IDが不正です" }, 400);
    const me = await currentUser(req, env);
    const { results } = await env.DB.prepare(
      "SELECT c.id, c.body, c.updated_at AS at, u.nick, u.admin AS staff, c.user_id = ? AS mine FROM comments c JOIN users u ON u.id = c.user_id " +
      "WHERE c.game_id = ? AND c.hidden = 0 AND u.banned = 0 ORDER BY c.updated_at DESC LIMIT 200"
    ).bind(me ? me.id : "", g).all();
    return json({ comments: results.map(r => ({ ...r, mine: !!r.mine, staff: !!r.staff })) });
  }
  if (p === "/api/comment-counts" && m === "GET") {
    const { results } = await env.DB.prepare(
      "SELECT c.game_id AS g, COUNT(*) AS n, MAX(c.updated_at) AS t FROM comments c JOIN users u ON u.id = c.user_id WHERE c.hidden = 0 AND u.banned = 0 GROUP BY c.game_id"
    ).all();
    // n: 作品ごとのコメント数、t: 作品ごとの最新コメントの日時
    return json({ n: Object.fromEntries(results.map(r => [r.g, r.n])), t: Object.fromEntries(results.map(r => [r.g, r.t])) }, 200, { "cache-control": "public, max-age=60" });
  }
  // 新着コメント（全作品）
  if (p === "/api/comments/latest" && m === "GET") {
    const limit = Math.min(50, Math.max(1, Number(url.searchParams.get("limit")) || 5));
    const { results } = await env.DB.prepare(
      "SELECT c.id, c.game_id AS g, c.body, c.updated_at AS at, u.nick, u.admin AS staff FROM comments c JOIN users u ON u.id = c.user_id " +
      "WHERE c.hidden = 0 AND u.banned = 0 ORDER BY c.updated_at DESC LIMIT ?"
    ).bind(limit).all();
    return json({ comments: results.map(r => ({ ...r, staff: !!r.staff })) }, 200, { "cache-control": "public, max-age=30" });
  }

  const me = await currentUser(req, env);
  if (p === "/api/me") {
    if (!me) return json({ guest: true, login: ready(env) });
    const out = { nick: me.nick, admin: !!me.admin };
    if (me.admin) {
      // 未対応の通報（表示中のコメント・利用停止していない人）の件数
      const r = await env.DB.prepare("SELECT COUNT(DISTINCT r.comment_id) AS n FROM reports r JOIN comments c ON c.id = r.comment_id JOIN users u ON u.id = c.user_id WHERE c.hidden = 0 AND u.banned = 0").first();
      out.reports = r ? r.n : 0;
    }
    return json(out);
  }
  if (!me) return json({ error: "ログインしてください" }, 401);

  if (p === "/api/logout" && m === "POST") {
    await env.DB.prepare("DELETE FROM sessions WHERE hash = ?").bind(await sha256(cookies(req)["__Host-hd_sid"])).run();
    return json({ ok: true }, 200, { "set-cookie": setCookie("__Host-hd_sid", "", 0) });
  }
  if (p === "/api/account" && m === "DELETE") {
    // 退会：この人に関するデータをすべて消す
    await env.DB.batch(["comments", "favs", "hides", "prefs", "sessions", "reports"].map(t =>
      env.DB.prepare(`DELETE FROM ${t} WHERE user_id = ?`).bind(me.id)).concat(
      env.DB.prepare("DELETE FROM users WHERE id = ?").bind(me.id)));
    return json({ ok: true }, 200, { "set-cookie": setCookie("__Host-hd_sid", "", 0) });
  }
  if (p === "/api/nick" && m === "POST") {
    const nick = clean(body.nick, NICK_MAX, 1);
    if (!nick) return json({ error: `ニックネームは1〜${NICK_MAX}文字で入力してください` }, 400);
    if (!me.admin && reserved(nick)) return json({ error: "運営と紛らわしい名前は使えません。別の名前にしてください" }, 400);
    await env.DB.prepare("UPDATE users SET nick = ? WHERE id = ?").bind(nick, me.id).run();
    return json({ ok: true, nick });
  }

  if (p === "/api/state" && m === "GET") {
    const [f, h, pr] = await env.DB.batch([
      env.DB.prepare("SELECT game_id, snap FROM favs WHERE user_id = ?").bind(me.id),
      env.DB.prepare("SELECT k FROM hides WHERE user_id = ?").bind(me.id),
      env.DB.prepare("SELECT data FROM prefs WHERE user_id = ?").bind(me.id),
    ]);
    return json({ favs: f.results.map(r => r.game_id), snaps: Object.fromEntries(f.results.filter(r => r.snap).map(r => [r.game_id, r.snap])), hides: h.results.map(r => r.k), prefs: pr.results[0] ? JSON.parse(pr.results[0].data) : null });
  }
  if (p === "/api/fav" && m === "POST") {
    if (!GAME_ID.test(body.g || "")) return json({ error: "作品IDが不正です" }, 400);
    const snap = typeof body.snap === "string" && body.snap.length <= 300 ? body.snap : null;
    if (body.on && await full(env, "favs", me.id)) return json({ error: `お気に入りは${LIMIT}件までです` }, 400);
    await (body.on
      ? env.DB.prepare("INSERT OR IGNORE INTO favs (user_id, game_id, created_at, snap) VALUES (?, ?, ?, ?)").bind(me.id, body.g, now(), snap)
      : env.DB.prepare("DELETE FROM favs WHERE user_id = ? AND game_id = ?").bind(me.id, body.g)).run();
    return json({ ok: true });
  }
  // お気に入りの「確認済みの状態」をまとめて更新する
  if (p === "/api/snaps" && m === "POST") {
    const items = Object.entries(body.items || {}).filter(([g, v]) => GAME_ID.test(g) && typeof v === "string" && v.length <= 300).slice(0, 1000);
    for (let i = 0; i < items.length; i += 50)
      await env.DB.batch(items.slice(i, i + 50).map(([g, v]) => env.DB.prepare("UPDATE favs SET snap = ? WHERE user_id = ? AND game_id = ?").bind(v, me.id, g)));
    return json({ ok: true });
  }
  if (p === "/api/hide" && m === "POST") {
    const k = String(body.k || "");
    if (!(GAME_ID.test(k) || /^s:.{1,80}$/.test(k))) return json({ error: "指定が不正です" }, 400);
    if (body.on && await full(env, "hides", me.id)) return json({ error: `非表示は${LIMIT}件までです` }, 400);
    await (body.on
      ? env.DB.prepare("INSERT OR IGNORE INTO hides (user_id, k, created_at) VALUES (?, ?, ?)").bind(me.id, k, now())
      : env.DB.prepare("DELETE FROM hides WHERE user_id = ? AND k = ?").bind(me.id, k)).run();
    return json({ ok: true });
  }
  if (p === "/api/prefs" && m === "POST") {
    const data = JSON.stringify(body.prefs ?? null);
    if (data.length > 2000) return json({ error: "設定が大きすぎます" }, 400);
    await env.DB.prepare("INSERT INTO prefs (user_id, data) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET data = excluded.data").bind(me.id, data).run();
    return json({ ok: true });
  }

  if (p === "/api/comments" && m === "POST") {
    if (!me.nick) return json({ error: "先にニックネームを決めてください" }, 400);
    const g = body.g || "";
    const text = clean(body.body, BODY_MAX);
    if (!GAME_ID.test(g)) return json({ error: "作品IDが不正です" }, 400);
    if (!text) return json({ error: `コメントは1〜${BODY_MAX}文字で入力してください` }, 400);
    // 連続投稿の防止（全作品あわせて10秒に1回まで）
    const last = await env.DB.prepare("SELECT MAX(updated_at) AS t FROM comments WHERE user_id = ?").bind(me.id).first();
    if (last && last.t && Date.now() - Date.parse(last.t) < 10000) return json({ error: "少し時間をおいてから投稿してください" }, 429);
    const t = now();
    await env.DB.prepare(
      "INSERT INTO comments (user_id, game_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?) " +
      "ON CONFLICT(user_id, game_id) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at"
    ).bind(me.id, g, text, t, t).run();
    return json({ ok: true });
  }
  if (p === "/api/comments" && m === "DELETE") {
    await env.DB.prepare("DELETE FROM comments WHERE user_id = ? AND game_id = ?").bind(me.id, url.searchParams.get("g") || "").run();
    return json({ ok: true });
  }
  if (p === "/api/report" && m === "POST") {
    const id = Number(body.id);
    if (!Number.isInteger(id)) return json({ error: "指定が不正です" }, 400);
    await env.DB.prepare("INSERT OR IGNORE INTO reports (comment_id, user_id, reason, created_at) VALUES (?, ?, ?, ?)")
      .bind(id, me.id, clean(body.reason, 100) || "", now()).run();
    return json({ ok: true });
  }

  // ---------- 管理（admin のみ） ----------
  if (p.startsWith("/api/admin/")) {
    if (!me.admin) return json({ error: "権限がありません" }, 403);
    if (p === "/api/admin/reports" && m === "GET") {
      const { results } = await env.DB.prepare(
        "SELECT c.id, c.game_id AS g, c.body, c.hidden, u.id AS uid, u.nick, u.banned, COUNT(r.user_id) AS n, MAX(r.created_at) AS last, " +
        "GROUP_CONCAT(r.reason, ' / ') AS reasons FROM reports r JOIN comments c ON c.id = r.comment_id JOIN users u ON u.id = c.user_id " +
        "GROUP BY c.id ORDER BY last DESC LIMIT 200"
      ).all();
      return json({ reports: results });
    }
    if (p === "/api/admin/comment" && m === "POST") {
      await env.DB.prepare("UPDATE comments SET hidden = ? WHERE id = ?").bind(body.hidden ? 1 : 0, Number(body.id)).run();
      if (!body.hidden) await env.DB.prepare("DELETE FROM reports WHERE comment_id = ?").bind(Number(body.id)).run();
      return json({ ok: true });
    }
    if (p === "/api/admin/ban" && m === "POST") {
      await env.DB.batch([
        env.DB.prepare("UPDATE users SET banned = ? WHERE id = ? AND admin = 0").bind(body.ban ? 1 : 0, String(body.uid)),
        env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(String(body.uid)),
      ]);
      return json({ ok: true });
    }
  }
  return json({ error: "見つかりません" }, 404);
}
