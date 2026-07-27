from datetime import datetime, timezone
import json
import os
import time
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
import requests
from requests.auth import HTTPBasicAuth

# ==========================================
# 🎯 1. 環境変数 & 設定
# ==========================================
DATA_URL = "https://boatrace-shinsum.com/"
USER_ID = os.environ.get("SHINSUM_USER", "sum")
PASSWORD = os.environ.get("SHINSUM_PASS", "art")

# Webhook URLs
ALERT_WEBHOOK_URL = os.environ.get(
    "MONITOR_DISCORD_WEBHOOK_URL"
)  # ⚡｜リアルタイムaiアラート
RESULT_WEBHOOK_URL = os.environ.get(
    "RESULT_DISCORD_WEBHOOK_URL"
)  # 🎯｜的中実績

# 💾 状態管理用ファイル
PENDING_RESULTS_FILE = "pending_results.json"  # リアルタイムアラート追跡用
PENDING_PICKUPS_FILE = (
    "pending_pickup_races.json"  # 朝一ピックアップ万舟追跡用
)

venue_name_map = {
    "kiryu": "桐生",
    "toda": "戸田",
    "edogawa": "江戸川",
    "tokoname": "常滑",
    "mikuni": "三国",
    "marugame": "丸亀",
    "miyajima": "宮島",
    "tokuyama": "徳山",
    "ashiya": "芦屋",
    "omura": "大村",
    "gamagori": "蒲郡",
    "hamanako": "浜名湖",
    "heiwajima": "平和島",
    "tamagawa": "多摩川",
    "tsu": "津",
    "biwako": "びわこ",
    "suminoe": "住之江",
    "amagasaki": "尼崎",
    "naruto": "鳴門",
    "karatsu": "唐津",
    "kojima": "児島",
    "wakamatsu": "若松",
    "fukuoka": "福岡",
    "shimonoseki": "下関",
}

session = requests.Session()
session.auth = HTTPBasicAuth(USER_ID, PASSWORD)
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
})


# ==========================================
# 📡 2. Discord 送信ヘルパー
# ==========================================
def send_discord(webhook_url, title, description, fields=[], color=0x00FF00):
  if not webhook_url:
    print(f"⚠️ Webhook URL未設定のためスキップ: {title}")
    return
  payload = {
      "embeds": [{
          "title": title,
          "description": description,
          "color": color,
          "fields": fields,
          "footer": {"text": "NEXUS-X Realtime AI Engine"},
          "timestamp": datetime.now(timezone.utc).isoformat(),
      }]
  }
  try:
    res = requests.post(webhook_url, json=payload, timeout=10)
    if res.status_code not in [200, 204]:
      print(f"⚠️ Discord送信エラー: HTTP {res.status_code}")
  except Exception as e:
    print(f"⚠️ Discord通信エラー: {e}")


# ==========================================
# 🔍 3. 結果チェック＆自動的中報告（メイン処理）
# ==========================================
def check_results():
  """リアルタイムアラート ＆ 朝一ピックアップ（万舟）の結果を自動検証"""

  # ----------------------------------------
  # A. リアルタイムアラートの結果回収
  # ----------------------------------------
  if os.path.exists(PENDING_RESULTS_FILE):
    try:
      with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
        pending = json.load(f)
    except Exception as e:
      print(f"⚠️ {PENDING_RESULTS_FILE} 読み込みエラー: {e}")
      pending = {}

    if pending:
      updated_pending = pending.copy()
      for key, info in list(pending.items()):
        clean_url = info.get("clean_url")
        rno = info.get("rno")
        venue_jp = info.get("venue_jp")
        alert_type = info.get("alert_type")
        recommended_combos = info.get("recommended_combos", [])

        # 結果ファイル参照
        res_url = f"{clean_url}/r{rno}/result.json"
        try:
          r = session.get(res_url, timeout=5)
          if r.status_code != 200:
            continue  # レース未終了または結果未確定

          result_data = r.json()
          sanrentan = result_data.get("sanrentan", {})
          winning_combo = sanrentan.get("combo")  # 例: "1-2-3"
          payout = sanrentan.get("payout", 0)  # 例: 1500

          if winning_combo:
            # 🎯 的中判定
            if winning_combo in recommended_combos:
              send_discord(
                  webhook_url=RESULT_WEBHOOK_URL,
                  title=f"🎯【AIアラート的中報告】 {venue_jp} {rno}R",
                  description=(
                      f"⚡ **{alert_type}** アラート配信のレースで見事的中しました！"
                  ),
                  fields=[
                      {
                          "name": "📍 対象レース",
                          "value": f"{venue_jp} {rno}R",
                          "inline": True,
                      },
                      {
                          "name": "🎲 確定出目",
                          "value": f"**3連単 {winning_combo}**",
                          "inline": True,
                      },
                      {
                          "name": "💰 払戻金",
                          "value": f"**{payout:,}円**",
                          "inline": True,
                      },
                  ],
                  color=0x00FF00,  # 的中カラー（緑）
              )
              print(f"🎯 的中報告送信: {venue_jp} {rno}R ({winning_combo})")

            # 確定したので結果待ちリストから削除
            del updated_pending[key]
        except Exception as e:
          print(f"⚠️ 結果参照エラー ({key}): {e}")

      # 更新したリストを書き戻し
      try:
        with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
          json.dump(updated_pending, f, ensure_ascii=False, indent=2)
      except Exception as e:
        print(f"⚠️ {PENDING_RESULTS_FILE} 保存エラー: {e}")

  # ----------------------------------------
  # B. 朝一ピックアップの万舟（10,000円以上）自動検知
  # ----------------------------------------
  if os.path.exists(PENDING_PICKUPS_FILE):
    try:
      with open(PENDING_PICKUPS_FILE, "r", encoding="utf-8") as f:
        pending_pickups = json.load(f)
    except Exception as e:
      print(f"⚠️ {PENDING_PICKUPS_FILE} 読み込みエラー: {e}")
      pending_pickups = {}

    if pending_pickups:
      updated_pickups = pending_pickups.copy()
      for race_key, info in list(pending_pickups.items()):
        v_name = info.get("v")
        rno = info.get("r")
        jcd = info.get("jcd")
        date_str = info.get("date")

        # 結果ファイル参照（shinsum 側のディレクトリ構造に合わせて取得）
        res_url = f"{DATA_URL}data/{jcd}/{date_str}/r{rno}/result.json"

        try:
          r = session.get(res_url, timeout=5)
          if r.status_code != 200:
            continue  # レース未終了

          result_data = r.json()
          sanrentan = result_data.get("sanrentan", {})
          winning_combo = sanrentan.get("combo")  # 例: "3-1-4"
          payout = sanrentan.get("payout", 0)  # 例: 12400

          if payout >= 10000:
            # 💣 万舟ヒット実績投稿！
            send_discord(
                webhook_url=RESULT_WEBHOOK_URL,
                title=f"💣【朝一ピックアップ万舟ヒット！】 {v_name} {rno}R",
                description=(
                    "朝一AI解析でピックアップした波乱期待値レースにて**万舟が発生**しました！"
                ),
                fields=[
                    {
                        "name": "📍 対象レース",
                        "value": f"{v_name} {rno}R",
                        "inline": True,
                    },
                    {
                        "name": "💰 確定配当",
                        "value": f"**3連単 {winning_combo} / {payout:,}円**",
                        "inline": True,
                    },
                    {
                        "name": "🔥 期待値スコア",
                        "value": f"{info.get('s', 0)}点",
                        "inline": True,
                    },
                ],
                color=0xFF0055,  # 豪華な万舟カラー（ピンク/ゴールド系）
            )
            print(f"💣 万舟ヒット検知＆投稿: {v_name} {rno}R ({payout:,}円)")

          # 成功・不的中を問わず確定したら除外
          del updated_pickups[race_key]
        except Exception as e:
          print(f"⚠️ 万舟結果参照エラー ({race_key}): {e}")

      # 更新したリストを書き戻し
      try:
        with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
          json.dump(updated_pickups, f, ensure_ascii=False, indent=2)
      except Exception as e:
        print(f"⚠️ {PENDING_PICKUPS_FILE} 保存エラー: {e}")


# ==========================================
# 🚀 4. メイン実行スクリプト
# ==========================================
def main():
  print("🚀 【NEXUS-X リアルタイム監視＆結果回収エンジン】 起動...")

  # 1. 未消化レースの結果チェック
  check_results()

  # 2. リアルタイムアラートの監視（既存のメイン処理を実行）
  # ※ここに既存のリアルタイムアラート検知ロジックが続きます
  # レース検知時に pending_results.json へ書き出す処理が入っていれば完了です！


if __name__ == "__main__":
  main()
