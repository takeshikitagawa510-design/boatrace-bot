import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import requests

JST = timezone(timedelta(hours=+9), "JST")

# 🎯 的中・万舟実績用 Webhook URL
RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL")

# 💾 追跡データファイル
PENDING_RESULTS_FILE = "pending_results.json"
PENDING_PICKUPS_FILE = "pending_pickup_races.json"

# 会場名 ➔ 公式場コード(01-24)
VENUE_NO_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05",
    "浜名湖": "06", "蒲郡": "07", "常滑": "08", "津": "09", "びわこ": "10",
    "住之江": "11", "尼崎": "12", "鳴門": "13", "丸亀": "14", "児島": "15",
    "宮島": "16", "徳山": "17", "下関": "18", "若松": "19", "芦屋": "20",
    "福岡": "21", "唐津": "22", "大村": "23", "三国": "24",
}


def clean_venue_name(raw_name):
    """[女子] や joshi などの余計な表記を削り、純粋な会場名（漢字）のみ抽出"""
    if not raw_name:
        return ""
    cleaned = re.sub(r"\[.*?\]|joshi|[a-zA-Z\s]", "", str(raw_name)).strip()
    return cleaned


def send_discord_embed(webhook_url, title, description, fields=[], color=0x00FF00):
    """DiscordへEmbedメッセージを送信"""
    if not webhook_url:
        print(f"⚠️ RESULT_WEBHOOK_URL未設定のためスキップ: {title}")
        return
    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {"text": "NEXUS-X VIP AI Engine"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📡 Discord送信結果: HTTP {res.status_code}")
    except Exception as e:
        print(f"⚠️ Discord通信エラー: {e}")


def fetch_official_sanrentan_result(venue_jp, rno, date_str=None):
    """
    BOAT RACE 公式サイト (boatrace.jp) から確実に3連単結果と払戻金を回収
    """
    clean_v = clean_venue_name(venue_jp)
    jcd = VENUE_NO_MAP.get(clean_v)
    if not jcd:
        print(f"⚠️ 未対応の会場名: '{venue_jp}' (整形後: '{clean_v}')")
        return None, 0

    if not date_str:
        date_str = datetime.now(JST).strftime("%Y%m%d")

    # 公式サイトのレース結果URL
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd}&hd={date_str}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None, 0

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 勝舟不成立・レース未確定チェック
        if "レース結果はありません" in resp.text or "データがありません" in resp.text:
            return None, 0

        # 3連単のテーブル・行を探す
        for tbody in soup.find_all("tbody"):
            text = tbody.get_text()
            if "3連単" in text:
                # 出目 (例: 1-2-3)
                combo_match = re.search(r"([1-6])\s*[-–—\-]\s*([1-6])\s*[-–—\-]\s*([1-6])", text)
                # 払戻金 (例: ¥1,230 や 1,230円)
                payout_match = re.search(r"[¥￥]?([0-9,]+)\s*円?", text)

                if combo_match and payout_match:
                    payout_str = payout_match.group(1).replace(",", "")
                    if payout_str.isdigit():
                        payout_val = int(payout_str)
                        if payout_val > 0:
                            combo_text = f"{combo_match.group(1)}-{combo_match.group(2)}-{combo_match.group(3)}"
                            return combo_text, payout_val

    except Exception as e:
        print(f"⚠️ 公式結果解析エラー ({venue_jp} {rno}R): {e}")

    return None, 0


def check_realtime_results():
    """リアルタイムAIアラートの的中自動判定"""
    if not os.path.exists(PENDING_RESULTS_FILE):
        return

    try:
        with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
            pending_results = json.load(f)
    except Exception:
        return

    if not pending_results:
        print("☕ 追跡中のリアルタイムアラートはありません。")
        return

    print(f"🔍 追跡中アラート ({len(pending_results)}件) の結果照会（公式）を開始...")
    updated_pending = pending_results.copy()

    for race_key, info in list(pending_results.items()):
        rno = info.get("rno")
        raw_v = info.get("venue_jp") or info.get("venue") or info.get("v") or ""
        venue_jp = clean_venue_name(raw_v)
        alert_type = info.get("alert_type")
        recommended_combos = info.get("recommended_combos", [])

        if not venue_jp or not rno:
            continue

        winning_combo, payout = fetch_official_sanrentan_result(venue_jp, rno)

        if winning_combo:
            print(f"   🏁 結果取得成功: {venue_jp} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
            is_hit = False
            for combo in recommended_combos:
                if not combo or combo == "対象なし" or len(combo) < 5:
                    continue
                
                parts = combo.replace("=", "-").split("-")
                if len(parts) == 3:
                    head, r2_list, r3_list = parts[0], list(parts[1]), list(parts[2])
                    win_parts = winning_combo.split("-")
                    if len(win_parts) == 3:
                        if (win_parts[0] in head and win_parts[1] in r2_list and win_parts[2] in r3_list):
                            is_hit = True
                            break

            if is_hit:
                print(f"   🎯 【的中】 Discordへ通知を送信します: {venue_jp} {rno}R")
                send_discord_embed(
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
            else:
                print(f"   💀 【不的中】 推奨: {recommended_combos} / 結果: {winning_combo}")

            if race_key in updated_pending:
                del updated_pending[race_key]
        else:
            print(f"   ⏳ 結果未確定または取得待ち: {venue_jp} {rno}R")

    try:
        with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_pending, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_RESULTS_FILE} 保存エラー: {e}")


def check_pickup_results():
    """朝一ピックアップ万舟ヒット（10,000円以上）自動チェック"""
    if not os.path.exists(PENDING_PICKUPS_FILE):
        return

    try:
        with open(PENDING_PICKUPS_FILE, "r", encoding="utf-8") as f:
            pending_pickups = json.load(f)
    except Exception:
        return

    if not pending_pickups:
        print("☕ 追跡中の朝一ピックアップはありません。")
        return

    print(f"🔍 追跡中ピックアップ ({len(pending_pickups)}件) の結果照会（公式）を開始...")
    updated_pickups = pending_pickups.copy()

    for race_key, info in list(pending_pickups.items()):
        raw_v = info.get("v") or info.get("venue") or info.get("venue_jp") or ""
        v_name = clean_venue_name(raw_v)
        rno = info.get("r") or info.get("rno") or info.get("race_no")
        date_str = str(info.get("date") or datetime.now(JST).strftime("%Y%m%d"))
        score = info.get("s") or info.get("score") or info.get("eval_score") or "高"

        if not v_name or not rno:
            continue

        winning_combo, payout = fetch_official_sanrentan_result(v_name, rno, date_str=date_str)

        if winning_combo:
            print(f"   🏁 ピックアップ結果取得成功: {v_name} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
            if payout >= 10000:
                print(f"   💣 【万舟達成】 Discordへ通知を送信します: {v_name} {rno}R ({payout:,}円)")
                send_discord_embed(
                    webhook_url=RESULT_WEBHOOK_URL,
                    title=f"💣【朝一ピックアップ万舟ヒット！】 {v_name} {rno}R",
                    description="朝一AI解析でピックアップした波乱期待値レースにて**万舟が発生**しました！",
                    fields=[
                        {"name": "📍 対象レース", "value": f"{v_name} {rno}R", "inline": True},
                        {"name": "💰 確定配当", "value": f"**3連単 {winning_combo} / {payout:,}円**", "inline": True},
                        {"name": "🔥 期待値スコア", "value": f"{score}点", "inline": True},
                    ],
                    color=0xFF0055,
                )
            else:
                print(f"   📉 【通常配当】 万舟対象外: {v_name} {rno}R ({payout:,}円)")

            if race_key in updated_pickups:
                del updated_pickups[race_key]
        else:
            print(f"   ⏳ ピックアップ結果未確定: {v_name} {rno}R")

    try:
        with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_pickups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_PICKUPS_FILE} 保存エラー: {e}")


if __name__ == "__main__":
    check_realtime_results()
    check_pickup_results()
