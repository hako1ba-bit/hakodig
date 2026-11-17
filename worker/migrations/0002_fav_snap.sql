-- お気に入りに「最後に確認したときの状態」を持たせる（変化のお知らせ用）
ALTER TABLE favs ADD COLUMN snap TEXT;
