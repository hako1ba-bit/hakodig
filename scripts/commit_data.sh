#!/bin/sh
# data/ に変更があれば保存して push する。ほかの実行と変更がぶつかったら、今回取得したデータを優先する
set -e
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data
if git diff --cached --quiet; then
  echo "変更なし"
  exit 0
fi
git commit -q -m "$1 $(TZ=Asia/Tokyo date '+%F %H:%M')"
for i in 1 2 3; do
  git fetch -q origin main
  if git rebase -q -X theirs origin/main; then
    if git push -q origin HEAD:main; then exit 0; fi
  else
    git rebase --abort || true
    exit 1
  fi
  sleep 5
done
exit 1
