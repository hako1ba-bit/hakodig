-- 届いたお知らせの履歴（1人あたり最新10件だけ残す）
CREATE TABLE notice_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  at TEXT NOT NULL,
  data TEXT NOT NULL
);
CREATE INDEX notice_log_user ON notice_log(user_id, id);
