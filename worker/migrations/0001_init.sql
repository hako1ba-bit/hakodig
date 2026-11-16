-- 利用者。Microsoft から受け取るサイト専用IDは、さらに秘密の値でハッシュ化して保存する（元のIDは残さない）
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  sub_hash TEXT NOT NULL UNIQUE,
  nick TEXT,
  admin INTEGER NOT NULL DEFAULT 0,
  banned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
-- ログイン状態。クッキーの値そのものは保存せず、ハッシュだけを持つ
CREATE TABLE sessions (
  hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX sessions_user ON sessions(user_id);
-- ひと言コメント（1作品につき1人1件）
CREATE TABLE comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  game_id TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  UNIQUE (user_id, game_id)
);
CREATE INDEX comments_game ON comments(game_id);
CREATE TABLE reports (
  comment_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (comment_id, user_id)
);
-- お気に入り・非表示（作品ID、またはシリーズ）・検索設定
CREATE TABLE favs (user_id TEXT NOT NULL, game_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (user_id, game_id));
CREATE TABLE hides (user_id TEXT NOT NULL, k TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (user_id, k));
CREATE TABLE prefs (user_id TEXT PRIMARY KEY, data TEXT NOT NULL);
