# ハコディグル

Xbox日本ストア検索サポート（非公式） by ハコイチバ
https://hako1ba-bit.github.io/hakosearch/

## しくみ

- **毎日 4:17（日本時間）** に GitHub Actions（「毎日の更新」）が自動で動き、ストアの一覧・価格・セール・サブスク・Play Anywhere を取り直し、言語情報をまだ取っていない作品から順に取得して、サイトを更新します。
- ページのデザイン（`src/template.html`）や別名の対応表（`data/aliases.json`）を変えると、「サイトの作り直し」が動いて数分で反映されます。
- ストアへの通信は1秒以上の間隔をあけて、順番に行います。

## フォルダ

| 場所 | 中身 |
|---|---|
| `src/template.html` | ページ本体のひな形 |
| `scripts/` | 取得（`update_list.py`, `update_details.py`）とサイト生成（`build.py`） |
| `data/catalog.jsonl` | 全作品の基本情報・価格・サブスク（1作品1行） |
| `data/details.jsonl` | 言語情報・Play Anywhere・説明文（1作品1行） |
| `data/low.jsonl` | 記録上の最安値（2026-11-14 から記録） |
| `data/aliases.json` | 別名の対応表（例: バイオハザード → bio, resident evil） |

## 別名の追加のしかた

`data/aliases.json` に1行足すだけです。左がタイトルに含まれる言葉、右が検索で使われそうな呼び方です。

```json
"バイオハザード": ["bio", "biohazard", "resident evil", "re"],
```

## 手動で更新を動かすとき

GitHub の「Actions」タブ →「毎日の更新」→「Run workflow」。
