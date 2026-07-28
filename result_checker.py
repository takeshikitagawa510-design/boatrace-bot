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

# 会場名 ➔ マクール用URL英字マップ
VENUE_EN_MAP = {
    "桐生": "kiryu", "戸田": "toda", "江戸川": "edogawa", "平和島": "heiwajima", "多摩川": "tamagawa",
    "浜名湖": "hamanako", "蒲郡": "gamagori", "常滑": "tokoname", "津": "tsu", "びわこ": "biwako",
    "住之江": "suminoe", "尼崎": "amagasaki", "鳴門": "naruto", "丸亀": "marugame", "児島": "kojima",
    "宮島": "miyajima", "徳山": "tokuyama", "下関": "shimonoseki", "若松": "wakamatsu", "芦屋": "ashiya",
    "福岡": "fukuoka", "唐津": "karatsu", "大村": "omura", "三国": "mikuni",
}


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


def fetch_macour_sanrentan_result(venue_jp, rno):
    """
    sp.macour.jp/{venue}/results/ から指定レースの結果と払戻金を抽出
    """
    clean_v = venue_jp.replace("[女子]", "").strip()
    v_en = VENUE_EN_MAP.get(clean_v)
    if not v_en:
        print(f"⚠️ 未対応の会場名: {clean_v}")
        return None, 0

    url = f"https://sp.macour.jp/{v_en}/results/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"⚠️ HTTPエラー ({resp.status_code}): {url}")
            return None, 0

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # レース結果一覧の行/要素をループ処理
        target_r_str = f"{rno}R"
        
        # テーブル行またはブロック要素を探索
        for elem in soup.find_all(["tr", "div", "li", "a"]):
            text = elem.get_text().replace(" ", "").replace("\n", "")
            
            # 対象のR（例: "1R" や "4R"）が含まれているか判定
            if target_r_str in text:
                # 艇番（1〜6）の3連複/3連単の並びをチェック
                # 画像の構造：数字 - 数字 - 数字 + 金額円
                digits = re.findall(r"[1-6]", text)
                payout_match = re.search(r"([0-9,]+)円", text)

                # 対象Rの記述のあとに、着順の3つの数字と金額が存在するか
                if len(digits) >= 3 and payout_match:
                    combo_text = f"{digits[0]}-{digits[1]}-{digits[2]}"
                    payout_val = int(payout_match.group(1).replace(",", ""))
                    
                    if payout_val > 0:
                        return combo_text, payout_val

    except Exception as e:
        print(f"⚠️ 通信/解析エラー ({venue_jp} {rno}R): {e}")

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

    print(f"🔍 追跡中アラート ({len(pending_results)}件) の結果照会（マクール一覧ページ）を開始...")
    updated_pending = pending_results.copy()

    for race_key, info in list(pending_results.items()):
        rno = info.get("rno")
        venue_jp = info.get("venue_jp")
        alert_type = info.get("alert_type")
        recommended_combos = info.get("recommended_combos", [])

        if not venue_jp or not rno:
            continue

        winning_combo, payout = fetch_macour_sanrentan_result(venue_jp, rno)

        if winning_combo:
            print(f"  🏁 取得成功: {venue_jp} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
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
                print(f"🎯 的中報告送信: {venue_jp} {rno}R ({winning_combo} / {payout:,}円)")

            if race_key in updated_pending:
                del updated_pending[race_key]
        else:
            print(f"  ⏳ 結果未確定または取得待ち: {venue_jp} {rno}R")

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

    print(f"🔍 追跡中ピックアップ ({len(pending_pickups)}件) の結果照会（マクール一覧ページ）を開始...")
    updated_pickups = pending_pickups.copy()

    for race_key, info in list(pending_pickups.items()):
        v_name = str(info.get("v") or info.get("venue") or info.get("venue_jp") or "").replace("[女子]", "").strip()
        rno = info.get("r") or info.get("rno") or info.get("race_no")
        score = info.get("s") or info.get("score") or info.get("eval_score") or "高"

        if not v_name or not rno:
            continue

        winning_combo, payout = fetch_macour_sanrentan_result(v_name, rno)

        if winning_combo:
            print(f"  🏁 ピックアップ取得成功: {v_name} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
            if payout >= 10000:
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
                print(f"💣 万舟ヒット通知完了: {v_name} {rno}R ({payout:,}円)")

            if race_key in updated_pickups:
                del updated_pickups[race_key]
        else:
            print(f"  ⏳ ピックアップ結果未確定: {v_name} {rno}R")

    try:
        with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_pickups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_PICKUPS_FILE} 保存エラー: {e}")


if __name__ == "__main__":
    check_realtime_results()
    check_pickup_results()
