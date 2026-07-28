from datetime import datetime, timezone, timedelta
import json
import os
import time
import requests
from requests.auth import HTTPBasicAuth

# 日本時間(JST)の取得
JST = timezone(timedelta(hours=9))

# ==========================================
# 🎯 1. 環境変数 & 設定
# ==========================================
DATA_URL = "https://boatrace-shinsum.com"  # 末尾のスラッシュを削除（二重スラッシュ防止）
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

venue_en_map = {v: k for k, v in venue_name_map.items()}

session = requests.Session()
session.auth = HTTPBasicAuth(USER_ID, PASSWORD)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
    except Exception as e:
        print(f"⚠️ Discord通信エラー: {e}")


# ==========================================
# ⚡ 3. リアルタイムレース解析＆アラート送信
# ==========================================
def run_realtime_monitor():
    """本日の開催レースを巡回し、危険条件（イン飛び等）を検知して事前アラート送信"""
    today_str = datetime.now(JST).strftime("%Y%m%d")
    print(f"⚡ リアルタイム解析スキャン実行中... (日付: {today_str})")

    # 古い追跡データの自動整理
    pending = {}
    if os.path.exists(PENDING_RESULTS_FILE):
        try:
            with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # 本日のデータのみ保持（日付が異なる古いデータは自動消去）
                pending = {k: v for k, v in loaded.items() if v.get("date") == today_str}
        except Exception:
            pending = {}

    # レースデータリスト取得 (例: race_list.json)
    list_url = f"{DATA_URL}/data/race_list.json"
    try:
        r = session.get(list_url, timeout=10)
        if r.status_code != 200:
            print("⚠️ race_list.json の取得に失敗しました。")
            return
        races = r.json()
    except Exception as e:
        print(f"⚠️ リアルタイムスキャンエラー: {e}")
        return

    # 各レースの解析
    for race in races:
        v_raw = str(race.get("venue", race.get("v", ""))).strip()
        rno = race.get("rno", race.get("r"))
        date_str = str(race.get("date", today_str))

        if date_str != today_str:
            continue

        venue_en = venue_en_map.get(v_raw, v_raw)
        venue_jp = venue_name_map.get(venue_en, v_raw)
        race_key = f"{venue_en}_{date_str}_{rno}r"

        # 既に通知済みのレースはスキップ
        if race_key in pending:
            continue

        # 個別レース詳細データの読み込み
        race_detail_url = f"{DATA_URL}/data/{venue_en}/{date_str}/r{rno}/race.json"
        try:
            res = session.get(race_detail_url, timeout=5)
            if res.status_code != 200:
                continue
            detail = res.json()

            # --- 💡 AI判定ロジック ---
            # 例: イン逃げ率スコア(ai_score)が低い、またはイン飛びフラグがある場合
            is_in_danger = detail.get("in_danger", False) or detail.get("ai_in_score", 100) < 45
            if is_in_danger:
                alert_type = "⚠️ 1号機 イン飛び警戒アラート"
                combos = detail.get("recommended_combos", ["2-1-3", "2-3-1", "3-1-2"])

                print(f"⚡ アラート検知: {venue_jp} {rno}R")
                send_discord(
                    webhook_url=ALERT_WEBHOOK_URL,
                    title=f"⚡【リアルタイムAIアラート】{venue_jp} {rno}R",
                    description=f"**{alert_type}**\n1号機の信頼度が低下しています。波乱展開に注意！",
                    fields=[
                        {"name": "📍 対象", "value": f"{venue_jp} {rno}R", "inline": True},
                        {"name": "🎯 推奨買い目", "value": ", ".join(combos), "inline": True},
                    ],
                    color=0xFF9900,
                )

                # 的中判定用に保存
                pending[race_key] = {
                    "clean_url": f"{DATA_URL}/data/{venue_en}/{date_str}",
                    "rno": rno,
                    "venue_jp": venue_jp,
                    "alert_type": alert_type,
                    "recommended_combos": combos,
                    "date": date_str,
                }
        except Exception as e:
            continue

    # 更新された状態を書き込み
    with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


# ==========================================
# 🔍 4. 結果チェック＆自動的中・万舟報告
# ==========================================
def check_results():
    """リアルタイムアラート的中 ＆ 朝一ピックアップ万舟の結果検証"""
    today_str = datetime.now(JST).strftime("%Y%m%d")

    # ----------------------------------------
    # A. リアルタイムアラートの的中判定・結果回収
    # ----------------------------------------
    if os.path.exists(PENDING_RESULTS_FILE):
        try:
            with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
        except Exception:
            pending = {}

        if pending:
            print(f"🔍 【A】リアルタイムアラート監視件数: {len(pending)}件")
            updated_pending = pending.copy()
            for key, info in list(pending.items()):
                # 日付が古いデータは無条件で削除
                if info.get("date") != today_str:
                    del updated_pending[key]
                    continue

                clean_url = info.get("clean_url")
                rno = info.get("rno")
                venue_jp = info.get("venue_jp")
                alert_type = info.get("alert_type")
                recommended_combos = info.get("recommended_combos", [])

                res_url = f"{clean_url}/r{rno}/result.json"
                try:
                    r = session.get(res_url, timeout=5)
                    if r.status_code != 200:
                        continue  # レース未確定

                    result_data = r.json()
                    sanrentan = result_data.get("sanrentan", {})
                    winning_combo = sanrentan.get("combo")
                    payout = sanrentan.get("payout", 0)

                    if winning_combo:
                        if winning_combo in recommended_combos:
                            send_discord(
                                webhook_url=RESULT_WEBHOOK_URL,
                                title=f"🎯【AIアラート的中報告】 {venue_jp} {rno}R",
                                description=f"⚡ **{alert_type}** アラート配信のレースで見事的中しました！",
                                fields=[
                                    {"name": "📍 対象レース", "value": f"{venue_jp} {rno}R", "inline": True},
                                    {"name": "🎲 確定出目", "value": f"**3連単 {winning_combo}**", "inline": True},
                                    {"name": "💰 払戻金", "value": f"**{payout:,}円**", "inline": True},
                                ],
                                color=0x00FF00,
                            )
                            print(f"🎯 的中報告送信: {venue_jp} {rno}R ({winning_combo})")

                        del updated_pending[key]
                except Exception as e:
                    print(f"⚠️ 結果参照エラー ({key}): {e}")

            with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(updated_pending, f, ensure_ascii=False, indent=2)

    # ----------------------------------------
    # B. 朝一ピックアップの万舟（10,000円以上）自動検知
    # ----------------------------------------
    if os.path.exists(PENDING_PICKUPS_FILE):
        try:
            with open(PENDING_PICKUPS_FILE, "r", encoding="utf-8") as f:
                pending_pickups = json.load(f)
        except Exception:
            pending_pickups = {}

        if pending_pickups:
            print(f"🔍 【B】朝一ピックアップ監視件数: {len(pending_pickups)}件")
            updated_pickups = pending_pickups.copy()
            for race_key, info in list(pending_pickups.items()):
                date_str = str(info.get("date", ""))

                # 日付が今日以外の場合は古いデータとして消去
                if date_str != today_str:
                    del updated_pickups[race_key]
                    continue

                v_name = str(info.get("v", "")).strip()
                rno = info.get("r")

                if v_name in venue_en_map:
                    venue_en = venue_en_map[v_name]
                    venue_jp = v_name
                elif v_name in venue_name_map:
                    venue_en = v_name
                    venue_jp = venue_name_map[v_name]
                else:
                    venue_en = v_name
                    venue_jp = v_name

                # 正しいURL形式（二重スラッシュ防止）
                res_url = f"{DATA_URL}/data/{venue_en}/{date_str}/r{rno}/result.json"
                print(f"🌐 確認中: {venue_jp} {rno}R -> {res_url}")

                try:
                    r = session.get(res_url, timeout=5)
                    print(f" └ HTTP status: {r.status_code}")

                    if r.status_code != 200:
                        print(" └ ⏳ レース未確定または未終了")
                        continue

                    result_data = r.json()
                    sanrentan = result_data.get("sanrentan", {})
                    winning_combo = sanrentan.get("combo")
                    payout = sanrentan.get("payout", 0)

                    print(f" └ 確定出目: {winning_combo} / 配当: {payout}円")

                    if winning_combo:
                        if payout >= 10000:
                            print(f" 💣 万舟検知！ Discord送信 ({payout:,}円)")
                            send_discord(
                                webhook_url=RESULT_WEBHOOK_URL,
                                title=f"💣【朝一ピックアップ万舟ヒット！】 {venue_jp} {rno}R",
                                description="朝一AI解析でピックアップした波乱期待値レースにて**万舟が発生**しました！",
                                fields=[
                                    {"name": "📍 対象レース", "value": f"{venue_jp} {rno}R", "inline": True},
                                    {"name": "💰 確定配当", "value": f"**3連単 {winning_combo} / {payout:,}円**", "inline": True},
                                    {"name": "🔥 期待値スコア", "value": f"{info.get('s', 0)}点", "inline": True},
                                ],
                                color=0xFF0055,
                            )
                        else:
                            print(" ℹ️ 10,000円未満のため通知スキップ")

                        # 結果確定のためリストから削除
                        del updated_pickups[race_key]

                except Exception as e:
                    print(f"⚠️ 万舟結果参照エラー ({race_key}): {e}")

            with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
                json.dump(updated_pickups, f, ensure_ascii=False, indent=2)


# ==========================================
# 🚀 5. メイン実行スクリプト
# ==========================================
def main():
    print("🚀 【NEXUS-X リアルタイム監視＆結果回収エンジン】 起動...")
    # 1. リアルタイム解析＆事前アラート送信
    run_realtime_monitor()
    # 2. レース結果の自動回収＆的中・万舟投稿
    check_results()


if __name__ == "__main__":
    main()
