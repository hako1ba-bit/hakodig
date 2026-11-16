#!/bin/sh
# data/ に変更があれば保存して push する
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data
if ! git diff --cached --quiet; then
  git commit -q -m "$1 $(TZ=Asia/Tokyo date '+%F %H:%M')"
  git pull -q --rebase origin main
  git push -q origin HEAD:main
fi
