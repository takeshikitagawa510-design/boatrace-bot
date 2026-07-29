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

# 会場名 ➔ 競艇日和/公式共通場コード(1-24)
VENUE_NO_MAP = {
    "桐生": 1, "戸田": 2, "江戸川": 3, "平和島": 4, "多摩川": 5,
    "浜名湖": 6, "蒲郡": 7, "常滑": 8, "津": 9, "びわこ": 10,
    "住之江": 11, "尼崎": 12, "鳴門": 13, "丸亀": 14, "児島": 15,
    "宮島": 16, "徳山": 17, "下関": 18, "若松": 19, "芦屋": 20,
    "福岡": 21, "唐津": 22, "大村": 23, "三国": 24,
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


def fetch_kyoteibiyori_sanrentan_result(venue_jp, rno, date_str=None):
    """
    競艇日和から対象Rの3連単結果を取得
    """
    clean_v = clean_venue_name(venue_jp)
    place_no = VENUE_NO_MAP.get(clean_v)
    if not place_no:
        print(f"⚠️ 未対応の会場名: '{venue_jp}' (整形後: '{clean_v}')")
        return None, 0

    # 日付未指定の場合はJST基準の今日（YYYYMMDD）
    if not date_str or len(str(date_str)) < 8:
        date_str = datetime.now(JST).strftime("%Y%m%d")
    else:
        # 2026-07-29 などのハイフン除去
        date_str = str(date_str).replace("-", "").replace("/", "")[:8]

    url = f"https://kyoteibiyori.com/race_result_all.php?place_no={place_no}&hiduke={date_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://kyoteibiyori.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"⚠️ 競艇日和 HTTPエラー {resp.status_code} (URL: {url})")
            return None, 0

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        text_all = soup.get_text()

        target_r = f"{rno}R"
        
        # 1. HTML内のテーブル要素から走査
        for table in soup.find_all("table"):
            t_text = table.get_text()
            if target_r in t_text and ("3連単" in t_text or "三連単" in t_text):
                combo_m = re.search(r"([1-6])\s*[-–—─=⇒>]\s*([1-6])\s*[-–—─=⇒>]\s*([1-6])", t_text)
                payout_m = re.search(r"([0-9,]+)\s*円", t_text)
                if combo_m and payout_m:
                    payout_val = int(payout_m.group(1).replace(",", ""))
                    if payout_val > 0:
                        combo_text = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                        return combo_text, payout_val

        # 2. 全テキストからの強行抽出（レースブロック切り出し）
        if target_r in text_all:
            # target_r (例: "5R") 以降の文字列を切り出し
            after_r = text_all.split(target_r, 1)[1]
            # 次のレース（例: "6R"）までの区間を抽出
            next_r_search = re.search(r"\d{1,2}R", after_r)
            r_block = after_r[:next_r_search.start()] if next_r_search else after_r[:1000]

            if "3連単" in r_block or "三連単" in r_block:
                combo_m = re.search(r"([1-6])\s*[-–—─=⇒>]\s*([1-6])\s*[-–—─=⇒>]\s*([1-6])", r_block)
                payout_m = re.search(r"([0-9,]+)\s*円", r_block)
                if combo_m and payout_m:
                    payout_val = int(payout_m.group(1).replace(",", ""))
                    if payout_val > 0:
                        combo_text = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                        return combo_text, payout_val

    except Exception as e:
        print(f"⚠️ 競艇日和 解析例外 ({venue_jp} {rno}R): {e}")

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

    print(f"🔍 追跡中アラート ({len(pending_results)}件) の結果照会（競艇日和）を開始...")
    updated_pending = pending_results.copy()

    for race_key, info in list(pending_results.items()):
        rno = info.get("rno")
        raw_v = info.get("venue_jp") or info.get("venue") or info.get("v") or ""
        venue_jp = clean_venue_name(raw_v)
        date_str = info.get("date") or info.get("d")
        alert_type = info.get("alert_type")
        recommended_combos = info.get("recommended_combos", [])

        if not venue_jp or not rno:
            continue

        winning_combo, payout = fetch_kyoteibiyori_sanrentan_result(venue_jp, rno, date_str=date_str)

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
        
        time.sleep(0.5)

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

    print(f"🔍 追跡中ピックアップ ({len(pending_pickups)}件) の結果照会（競艇日和）を開始...")
    updated_pickups = pending_pickups.copy()

    for race_key, info in list(pending_pickups.items()):
        raw_v = info.get("v") or info.get("venue") or info.get("venue_jp") or ""
        v_name = clean_venue_name(raw_v)
        rno = info.get("r") or info.get("rno") or info.get("race_no")
        date_str = str(info.get("date") or info.get("d") or datetime.now(JST).strftime("%Y%m%d"))
        score = info.get("s") or info.get("score") or info.get("eval_score") or "高"

        if not v_name or not rno:
            continue

        winning_combo, payout = fetch_kyoteibiyori_sanrentan_result(v_name, rno, date_str=date_str)

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
            
        time.sleep(0.5)

    try:
        with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_pickups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_PICKUPS_FILE} 保存エラー: {e}")


if __name__ == "__main__":
    check_realtime_results()
    check_pickup_results()
