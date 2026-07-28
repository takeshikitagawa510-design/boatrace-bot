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
ALERT_WEBHOOK_URL = os.environ.get("MONITOR_DISCORD_WEBHOOK_URL")  # ⚡｜リアルタイムaiアラート
RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL")   # 🎯｜的中実績

# 💾 状態管理用ファイル
PENDING_RESULTS_FILE = "pending_results.json"        # リアルタイムアラート追跡用
PENDING_PICKUPS_FILE = "pending_pickup_races.json"  # 朝一ピックアップ万舟追跡用

venue_name_map = {
    "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川", "tokoname": "常滑",
    "mikuni": "三国", "marugame": "丸亀", "miyajima": "宮島", "tokuyama": "徳山",
    "ashiya": "芦屋", "omura": "大村", "gamagori": "蒲郡", "hamanako": "浜名湖",
    "heiwajima": "平和島", "tamagawa": "多摩川", "tsu": "津", "biwako": "びわこ",
    "suminoe": "住之江", "amagasaki": "尼崎", "naruto": "鳴門", "karatsu": "唐津",
    "kojima": "児島", "wakamatsu": "若松", "fukuoka": "福岡", "shimonoseki": "下関",
}

# 日本語場名から英語場名に変換する辞書（URL構築用）
venue_en_map = {v: k for k, v in venue_name_map.items()}

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
        print(f"📡 Discord送信結果: HTTP {res.status_code}")
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
            print(f"🔍 【A】リアルタイムアラート監視件数: {len(pending)}件")
            updated_pending = pending.copy()
            for key, info in list(pending.items()):
                clean_url = info.get("clean_url")
                rno = info.get("rno")
                venue_jp = info.get("venue_jp")
                alert_type = info.get("alert_type")
                recommended_combos = info.get("recommended_combos", [])

                res_url = f"{clean_url}/r{rno}/result.json"
                try:
                    r = session.get(res_url, timeout=5)
                    if r.status_code != 200:
                        continue  # レース未終了または結果未確定

                    result_data = r.json()
                    sanrentan = result_data.get("sanrentan", {})
                    winning_combo = sanrentan.get("combo")
                    payout = sanrentan.get("payout", 0)

                    if winning_combo:
                        if winning_combo in recommended_combos:
                            send_discord(
                                webhook_url=RESULT_WEBHOOK_URL,
                                title=f"🎯【AIアラート的中報告】 {venue_jp} {rno}R",
                                description=(
                                    f"⚡ **{alert_type}**"
                                    " アラート配信のレースで見事的中しました！"
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
                                color=0x00FF00,
                            )
                            print(
                                f"🎯 的中報告送信: {venue_jp} {rno}R"
                                f" ({winning_combo})"
                            )

                        del updated_pending[key]
                except Exception as e:
                    print(f"⚠️ 結果参照エラー ({key}): {e}")

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
            print(f"🔍 【B】朝一ピックアップ監視件数: {len(pending_pickups)}件")
            updated_pickups = pending_pickups.copy()
            for race_key, info in list(pending_pickups.items()):
                v_name = str(info.get("v", "")).strip()
                rno = info.get("r")
                date_str = info.get("date")

                # 日本語名(三国)・英語名(mikuni) どちらが格納されていても安全に英語場名を取得
                if v_name in venue_en_map:
                    venue_en = venue_en_map[v_name]
                    venue_jp = v_name
                elif v_name in venue_name_map:
                    venue_en = v_name
                    venue_jp = venue_name_map[v_name]
                else:
                    venue_en = v_name
                    venue_jp = v_name

                # 結果データURLの組み立て
                res_url = (
                    f"{DATA_URL}data/{venue_en}/{date_str}/r{rno}/result.json"
                )
                print(f"🌐 確認中: {venue_jp} {rno}R -> {res_url}")

                try:
                    r = session.get(res_url, timeout=5)
                    print(f" └ HTTP status: {r.status_code}")

                    if r.status_code != 200:
                        print(" └ ⏳ 結果未確定またはアクセス失敗（スキップ）")
                        continue  # レース未終了または結果未確定

                    result_data = r.json()
                    sanrentan = result_data.get("sanrentan", {})
                    winning_combo = sanrentan.get("combo")
                    payout = sanrentan.get("payout", 0)

                    print(f" └ 確定出目: {winning_combo} / 配当: {payout}円")

                    # レース結果が出ている場合
                    if winning_combo:
                        if payout >= 10000:
                            # 💣 万舟ヒット実績投稿！
                            print(f" 💣 万舟検知！ Discord送信を試みます ({payout:,}円)")
                            send_discord(
                                webhook_url=RESULT_WEBHOOK_URL,
                                title=(
                                    "💣【朝一ピックアップ万舟ヒット！】"
                                    f" {venue_jp} {rno}R"
                                ),
                                description=(
                                    "朝一AI解析でピックアップした波乱期待値レースにて**万舟が発生**しました！"
                                ),
                                fields=[
                                    {
                                        "name": "📍 対象レース",
                                        "value": f"{venue_jp} {rno}R",
                                        "inline": True,
                                    },
                                    {
                                        "name": "💰 確定配当",
                                        "value": (
                                            f"**3連単 {winning_combo} /"
                                            f" {payout:,}円**"
                                        ),
                                        "inline": True,
                                    },
                                    {
                                        "name": "🔥 期待値スコア",
                                        "value": f"{info.get('s', 0)}点",
                                        "inline": True,
                                    },
                                ],
                                color=0xFF0055,
                            )
                            print(
                                f"💣 万舟ヒット検知＆投稿完了: {venue_jp} {rno}R"
                                f" ({payout:,}円)"
                            )
                        else:
                            print(" ℹ️ 払戻金が10,000円未満のため通知スキップ")

                        # 結果が確定したら（万舟でも不的中でも）リストから削除
                        del updated_pickups[race_key]

                except Exception as e:
                    print(f"⚠️ 万舟結果参照エラー ({race_key}): {e}")

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
    check_results()


if __name__ == "__main__":
    main()
