import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

JST = timezone(timedelta(hours=+9), "JST")

RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL")
PENDING_RESULTS_FILE = "pending_results.json"
PENDING_PICKUPS_FILE = "pending_pickup_races.json"

# 🎯 競艇日和（kyoteibiyori.com）の正確な場コード(1-24)
VENUE_NO_MAP = {
    "桐生": 1,   "戸田": 2,   "江戸川": 3, "平和島": 4, "多摩川": 5,
    "浜名湖": 6, "蒲郡": 7,   "常滑": 8,   "津": 9,     "三国": 10,
    "びわこ": 11, "住之江": 12, "尼崎": 13, "鳴門": 14, "丸亀": 15,
    "児島": 16,  "宮島": 17,  "徳山": 18, "下関": 19, "若松": 20,
    "芦屋": 21,  "福岡": 22,  "唐津": 23, "大村": 24,
}

def clean_venue_name(raw_name):
    if not raw_name:
        return ""
    return re.sub(r"\[.*?\]|joshi|[a-zA-Z\s]", "", str(raw_name)).strip()

def send_discord_embed(webhook_url, title, description, fields=[], color=0x00FF00):
    if not webhook_url:
        print(f"⚠️ RESULT_WEBHOOK_URL未設定のためスキップ: {title}")
        return
    import requests
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

def fetch_sanrentan_with_browser(page, venue_jp, rno, date_str=None):
    clean_v = clean_venue_name(venue_jp)
    place_no = VENUE_NO_MAP.get(clean_v)
    if not place_no:
        print(f"⚠️ 未対応の会場名: '{venue_jp}' (整形後: '{clean_v}')")
        return None, 0

    if not date_str or len(str(date_str)) < 8:
        raw_date = datetime.now(JST).strftime("%Y%m%d")
    else:
        raw_date = str(date_str).replace("-", "").replace("/", "")[:8]

    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    url = f"https://kyoteibiyori.com/race_result_all.php?place_no={place_no}&hiduke={formatted_date}"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        title = page.title()
        text_content = page.inner_text("body")

        if "ページが見つかりません" in title:
            url_alt = f"https://kyoteibiyori.com/race_result_all.php?place_no={place_no}&hiduke={raw_date}"
            page.goto(url_alt, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            text_content = page.inner_text("body")

        target_r = f"{rno}R"
        if target_r in text_content:
            after_r = text_content.split(target_r, 1)[1]
            next_r = re.search(r"\d{1,2}R", after_r)
            block = after_r[:next_r.start()] if next_r else after_r[:1000]

            if "3連単" in block or "三連単" in block:
                combo_m = re.search(r"([1-6])\s*[-–—─=⇒>]\s*([1-6])\s*[-–—─=⇒>]\s*([1-6])", block)
                payout_m = re.search(r"([0-9,]+)\s*円", block)
                if combo_m and payout_m:
                    payout_val = int(payout_m.group(1).replace(",", ""))
                    if payout_val > 0:
                        combo_text = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                        return combo_text, payout_val

    except Exception as e:
        print(f"⚠️ ブラウザ取得エラー ({venue_jp} {rno}R): {e}")

    return None, 0

def check_all_results():
    if not os.path.exists(PENDING_RESULTS_FILE) and not os.path.exists(PENDING_PICKUPS_FILE):
        print("☕ 追跡対象のデータが存在しません。")
        return

    today_str = datetime.now(JST).strftime("%Y%m%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()

        # 1. リアルタイムアラート判定
        if os.path.exists(PENDING_RESULTS_FILE):
            with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
                pending_results = json.load(f)

            if pending_results:
                updated_pending = {}
                # 当日以外の古いデータを取り除くクリーンアップ
                for k, v in pending_results.items():
                    d = str(v.get("date") or v.get("d") or "").replace("-", "").replace("/", "")[:8]
                    if not d or d == today_str:
                        updated_pending[k] = v
                    else:
                        print(f"🗑️ 古いアラートデータを削除: {k} (日付: {d})")

                print(f"🔍 追跡中アラート ({len(updated_pending)}件) の結果照会を開始...")

                for race_key, info in list(updated_pending.items()):
                    rno = info.get("rno")
                    venue_jp = clean_venue_name(info.get("venue_jp") or info.get("venue") or info.get("v") or "")
                    date_str = info.get("date") or info.get("d")
                    alert_type = info.get("alert_type")
                    recommended_combos = info.get("recommended_combos", [])

                    if not venue_jp or not rno:
                        continue

                    winning_combo, payout = fetch_sanrentan_with_browser(page, venue_jp, rno, date_str)

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
                                if len(win_parts) == 3 and (win_parts[0] in head and win_parts[1] in r2_list and win_parts[2] in r3_list):
                                    is_hit = True
                                    break

                        if is_hit:
                            print(f"   🎯 【的中】 Discord通知送信: {venue_jp} {rno}R")
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

                        del updated_pending[race_key]
                    else:
                        print(f"   ⏳ 未確定/取得待ち: {venue_jp} {rno}R")

                with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(updated_pending, f, ensure_ascii=False, indent=2)

        # 2. 朝一ピックアップ判定
        if os.path.exists(PENDING_PICKUPS_FILE):
            with open(PENDING_PICKUPS_FILE, "r", encoding="utf-8") as f:
                pending_pickups = json.load(f)

            if pending_pickups:
                updated_pickups = {}
                # 当日以外の古いデータを取り除くクリーンアップ
                for k, v in pending_pickups.items():
                    d = str(v.get("date") or v.get("d") or "").replace("-", "").replace("/", "")[:8]
                    if not d or d == today_str:
                        updated_pickups[k] = v
                    else:
                        print(f"🗑️ 古いピックアップデータを削除: {k} (日付: {d})")

                print(f"🔍 追跡中ピックアップ ({len(updated_pickups)}件) の結果照会を開始...")

                for race_key, info in list(updated_pickups.items()):
                    v_name = clean_venue_name(info.get("v") or info.get("venue") or info.get("venue_jp") or "")
                    rno = info.get("r") or info.get("rno") or info.get("race_no")
                    date_str = str(info.get("date") or info.get("d") or today_str)
                    score = info.get("s") or info.get("score") or info.get("eval_score") or "高"

                    if not v_name or not rno:
                        continue

                    winning_combo, payout = fetch_sanrentan_with_browser(page, v_name, rno, date_str)

                    if winning_combo:
                        print(f"   🏁 ピックアップ結果取得成功: {v_name} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
                        if payout >= 10000:
                            print(f"   💣 【万舟達成】 Discord通知送信: {v_name} {rno}R")
                            send_discord_embed(
                                webhook_url=RESULT_WEBHOOK_URL,
                                title=f"💣【朝一ピックアップ万舟ヒット！】 {v_name} {rno}R",
                                description="朝一AI解析でピックアップした波乱期待値レースにて**万舟が発生**しました！",
                                fields=[
                                    {"name": "📍 対象レース", "value": f"{v_name} {rno}R", "inline": True},
                                    {"name": "💰 確定配当", "value": f"**3连単 {winning_combo} / {payout:,}円**", "inline": True},
                                    {"name": "🔥 期待値スコア", "value": f"{score}点", "inline": True},
                                ],
                                color=0xFF0055,
                            )
                        else:
                            print(f"   📉 【通常配当】 万舟対象外: {v_name} {rno}R ({payout:,}円)")

                        del updated_pickups[race_key]
                    else:
                        print(f"   ⏳ ピックアップ結果未確定: {v_name} {rno}R")

                with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
                    json.dump(updated_pickups, f, ensure_ascii=False, indent=2)

        browser.close()

if __name__ == "__main__":
    check_all_results()
