name: 1. Nightly Data Update & Scoring Build

on:
  schedule:
    # 日本時間 23:30 (UTC 14:30) に実行
    - cron: '30 14 * * *'
  workflow_dispatch:

jobs:
  update-data:
    runs-on: ubuntu-latest
    steps:
      - name: リポジトリのチェックアウト
        uses: actions/checkout@v3

      - name: Python環境構築
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: パッケージインストール
        run: |
          pip install requests bs4 curl_cffi pandas

      - name: データ更新 ＆ 辞書生成スクリプト実行
        run: python update_data.py

      - name: 更新されたCSVとJSONをGitHubへ自動保存
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add manshu_half_year_recovery.csv scoring_dictionary.json
          git status
          git commit -m "Auto update: CSV and scoring_dictionary [skip ci]" || exit 0
          git push
