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

# 会場名 ➔ マクール用場コード(01-24)
VENUE_JCD_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04", "多摩川": "05",
    "浜名湖": "06", "蒲郡": "07", "常滑": "08", "津": "09", "びわこ": "10",
    "住之江": "11", "尼崎": "12", "鳴門": "13", "丸亀": "14", "児島": "15",
    "宮島": "16", "徳山": "17", "下関": "18", "若松": "19", "芦屋": "20",
    "福岡": "21", "唐津": "22", "大村": "23", "三国": "24",
}


def send_discord_embed(webhook_url, title, description, fields=[], color=0x00FF00):
    """DiscordへリッチなEmbed（カード型）メッセージを送信"""
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


def fetch_macour_sanrentan_result(venue_jp, rno, date_str=None, max_retries=2):
    """
    ボートレースマクール (sp.macour.jp) から3連単の結果と払戻金を回収
    """
    clean_v = venue_jp.replace("[女子]", "").strip()
    jcd = VENUE_JCD_MAP.get(clean_v)
    if not jcd:
        print(f"⚠️ 未対応の会場名: {clean_v}")
        return None, 0

    if not date_str:
        date_str = datetime.now(JST).strftime("%Y%m%d")

    # マクールスマホ版 払戻金URL
    url = f"https://sp.macour.jp/s/payout/?jcd={jcd}&date={date_str}&rno={rno}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36"
        )
    }

    # 連続アクセス負荷軽減のためのウェイト (1秒)
    time.sleep(1.0)

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue

            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")

            # ページ内のテキスト全検索＆テーブル解析
            full_text = soup.get_text()
            if "3連単" not in full_text and "三連単" not in full_text:
                # まだ確定していない（またはレース開催前）
                return None, 0

            for tr in soup.find_all("tr"):
                text = tr.get_text().replace(" ", "").replace("\n", "")
                if "3連単" in text or "三連単" in text:
                    # 出目パターン抽出 (例: 1-2-3 や 1=2=3)
                    m_combo = re.search(r"([1-6])[-=–—─=]([1-6])[-=–—─=]([1-6])", text)
                    # 払戻金抽出 (例: 1,230円 や ¥1230)
                    m_pay = re.search(r"([0-9,]+)円?", text)

                    combo_text = ""
                    payout_val = 0

                    if m_combo:
                        combo_text = f"{m_combo.group(1)}-{m_combo.group(2)}-{m_combo.group(3)}"

                    # 数値抽出（払戻金テーブルの各セルを確認）
                    tds = tr.find_all(["td", "th"])
                    for td in tds:
                        t_str = td.get_text().strip().replace(",", "").replace("円", "").replace("¥", "")
                        if t_str.isdigit():
                            val = int(t_str)
                            if val >= 100:  # 100円以上の払戻金額を判定
                                payout_val = val

                    if combo_text and payout_val > 0:
                        return combo_text, payout_val

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.5)
                continue
            else:
                print(f"⚠️ マクール結果取得エラー ({clean_v} {rno}R): タイムアウトまたは通信エラー")

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

    print(f"🔍 追跡中アラート ({len(pending_results)}件) の結果照会（マクール）を開始...")
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
            is_hit = False
            for combo in recommended_combos:
                if not combo or combo == "対象なし" or len(combo) < 5:
                    continue
                parts = combo.split("-")
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

            # レース確定後は追跡から削除
            if race_key in updated_pending:
                del updated_pending[race_key]

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

    print(f"🔍 追跡中ピックアップ ({len(pending_pickups)}件) の結果照会（マクール）を開始...")
    updated_pickups = pending_pickups.copy()

    for race_key, info in list(pending_pickups.items()):
        v_name = str(info.get("v") or info.get("venue") or info.get("venue_jp") or "").replace("[女子]", "").strip()
        rno = info.get("r") or info.get("rno") or info.get("race_no")
        date_str = str(info.get("date") or datetime.now(JST).strftime("%Y%m%d"))
        score = info.get("s") or info.get("score") or info.get("eval_score") or "高"

        if not v_name or not rno:
            continue

        winning_combo, payout = fetch_macour_sanrentan_result(v_name, rno, date_str=date_str)

        if winning_combo:
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

            # レース確定後は追跡から削除
            if race_key in updated_pickups:
                del updated_pickups[race_key]

    try:
        with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_pickups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_PICKUPS_FILE} 保存エラー: {e}")


if __name__ == "__main__":
    check_realtime_results()
    check_pickup_results()
