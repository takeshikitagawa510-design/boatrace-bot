import json
import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=+9), "JST")

# 既存のWebhook（IFTTTが監視しているチャンネル：万舟のみ送信）
RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL", "").strip()
# 新設のWebhook（全的中を記録するチャンネル）
ALL_RESULT_WEBHOOK_URL = os.environ.get("ALL_RESULT_DISCORD_WEBHOOK_URL", "").strip()

# Cloudflare Workers 中継URL
BOATRACE_PROXY_BASE = "https://boatrace-proxy.takeshi-kitagawa510.workers.dev"

PENDING_RESULTS_FILE = "pending_results.json"
PENDING_PICKUPS_FILE = "pending_pickup_races.json"

VENUE_NO_MAP = {
    "桐生": 1,   "戸田": 2,   "江戸川": 3, "平和島": 4, "多摩川": 5, "tamagawa": 5, "tamakawa": 5,
    "浜名湖": 6, "蒲郡": 7,   "常滑": 8,   "津": 9,     "三国": 10,
    "びわこ": 11, "住之江": 12, "尼崎": 13, "鳴門": 14, "丸亀": 15,
    "児島": 16,  "宮島": 17,  "徳山": 18, "下関": 19, "若松": 20,
    "芦屋": 21,  "福岡": 22,  "唐津": 23, "大村": 24,
}

SLUG_VENUE_MAP = {
    "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川", "heiwajima": "平和島",
    "tamagawa": "多摩川", "tamakawa": "多摩川", "hamanako": "浜名湖", "gamagori": "蒲郡", "tokoname": "常滑",
    "tsu": "津", "mikuni": "三国", "biwako": "びわこ", "suminoe": "住之江",
    "amagasaki": "尼崎", "naruto": "鳴門", "marugame": "丸亀", "kojima": "児島",
    "miyajima": "宮島", "tokuyama": "徳山", "shimonoseki": "下関", "wakamatsu": "若松",
    "ashiya": "芦屋", "fukuoka": "福岡", "karatsu": "唐津", "omura": "大村"
}

def resolve_venue_name(raw_venue, clean_url="", race_key=""):
    for jp_name in VENUE_NO_MAP.keys():
        if len(jp_name) >= 2:
            if jp_name in str(raw_venue) or jp_name in str(race_key):
                return jp_name

    target_str = f"{raw_venue} {clean_url} {race_key}".lower()
    for slug, jp_name in SLUG_VENUE_MAP.items():
        if slug in target_str:
            return jp_name

    cleaned = re.sub(r"\[.*?\]|joshi|女子競艇|[a-zA-Z0-9_\s]", "", str(raw_venue)).strip()
    if cleaned in VENUE_NO_MAP:
        return cleaned

    return ""

def send_discord_text(webhook_url, label, title, description, fields=[]):
    if not webhook_url:
        print(f"⚠️ [{label}] Webhook URLが未設定のため送信スキップ: {title}")
        return

    formatted_fields = []
    for f in fields:
        name = f['name']
        val = str(f['value']).replace("**", "").replace("`", "")
        formatted_fields.append(f"{name}\n{val}")
    
    fields_block = "\n".join(formatted_fields)
    plain_content = (
        f"{title}\n"
        f"{description}\n"
        f"{fields_block}"
    ).replace("**", "").replace("`", "")

    payload = {"content": plain_content}
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📡 [{label}] Discord送信結果: HTTP {res.status_code}")
    except Exception as e:
        print(f"⚠️ [{label}] Discord通信エラー: {e}")

def fetch_race_result_via_proxy(place_no, rno, raw_date):
    """
    Cloudflare Workers 中継経由で公式サイト(boatrace.jp)から3連単確定出目と払戻金を取得する（リトライ付き）
    """
    url = f"{BOATRACE_PROXY_BASE}/owpc/pc/race/raceresult?rno={rno}&jcd={place_no:02d}&hd={raw_date}"
    soup = None

    for attempt in range(2):
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                break
        except Exception as e:
            if attempt == 1:
                print(f"    ⚠️ 通信エラー (jcd={place_no:02d}, rno={rno}): {e}")
            else:
                time.sleep(0.5)

    if soup is None:
        return None, None

    page_text = soup.get_text(" ", strip=True)
    if "レース中止" in page_text or "不成立" in page_text:
        return "中止", 0

    for table in soup.find_all("table"):
        t_text = table.get_text(" ", strip=True)
        if "3連単" not in t_text and "３連単" not in t_text:
            continue

        for row in table.find_all("tr"):
            r_text = row.get_text(" ", strip=True)
            if "3連単" not in r_text and "３連単" not in r_text:
                continue

            m_combo = re.search(r"([1-6])\s*[-－–—]\s*([1-6])\s*[-－–—]\s*([1-6])", r_text)
            if m_combo:
                combo = f"{m_combo.group(1)}-{m_combo.group(2)}-{m_combo.group(3)}"
            else:
                nums = [
                    sp.get_text(strip=True)
                    for sp in row.find_all(["span", "div", "td"])
                    if sp.get_text(strip=True) in ["1", "2", "3", "4", "5", "6"]
                ]
                dedup_nums = []
                for n in nums:
                    if not dedup_nums or dedup_nums[-1] != n:
                        dedup_nums.append(n)
                if len(dedup_nums) >= 3:
                    combo = f"{dedup_nums[0]}-{dedup_nums[1]}-{dedup_nums[2]}"
                else:
                    continue

            m_pay = re.search(r"[¥￥]?\s*([1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]{2,5})\s*円?", r_text)
            if m_pay:
                payout = int(m_pay.group(1).replace(",", ""))
                if payout >= 100:
                    return combo, payout

    return None, None

def check_all_results():
    if not os.path.exists(PENDING_RESULTS_FILE) and not os.path.exists(PENDING_PICKUPS_FILE):
        print("☕ 追跡対象のデータが存在しません。")
        return

    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y%m%d")
    yesterday_str = (now_jst - timedelta(days=1)).strftime("%Y%m%d")

    if os.path.exists(PENDING_RESULTS_FILE):
        try:
            with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
                pending_results = json.load(f)
        except Exception as e:
            print(f"⚠️ {PENDING_RESULTS_FILE} 読み込みエラー: {e}")
            pending_results = {}

        if pending_results:
            updated_pending = {}
            for k, v in pending_results.items():
                d = str(v.get("date") or v.get("d") or "").replace("-", "").replace("/", "")[:8]
                # 日付跨ぎ直後でも取りこぼさないよう、当日と前日分を保持
                if not d or d in (today_str, yesterday_str):
                    updated_pending[k] = v
                else:
                    print(f"🗑️ 古いアラートデータを削除: {k} (日付: {d})")

            print(f"🔍 追跡中アラート ({len(updated_pending)}件) の結果照会を開始（Cloudflare中継）...")
            result_cache = {}

            for race_key, info in list(updated_pending.items()):
                rno = int(info.get("rno", 0))
                raw_date = str(info.get("date") or info.get("d") or today_str).replace("-", "").replace("/", "")[:8]
                raw_venue_jp = info.get("venue_jp") or info.get("venue") or info.get("v") or ""
                clean_url = info.get("clean_url", "")
                alert_type = info.get("alert_type", "AIアラート")
                recommended_combos = info.get("recommended_combos", [])

                resolved_v = resolve_venue_name(raw_venue_jp, clean_url, race_key)
                place_no = VENUE_NO_MAP.get(resolved_v)
                if not resolved_v or not place_no:
                    print(f"    ⚠️ 会場不明のためスキップ削除: {raw_venue_jp} {rno}R (key: {race_key})")
                    del updated_pending[race_key]
                    continue

                cache_key = (place_no, rno, raw_date)
                if cache_key in result_cache:
                    winning_combo, payout = result_cache[cache_key]
                else:
                    winning_combo, payout = fetch_race_result_via_proxy(place_no, rno, raw_date)
                    if winning_combo:
                        result_cache[cache_key] = (winning_combo, payout)
                    time.sleep(0.2)

                if winning_combo == "中止":
                    print(f"    🚫 レース中止のため追跡終了: {resolved_v} {rno}R")
                    del updated_pending[race_key]
                elif winning_combo and payout:
                    print(f"    🏁 結果取得成功: {resolved_v} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
                    is_hit = False
                    for combo in recommended_combos:
                        if not combo or combo == "対象なし":
                            continue

                        # ① 単体出目（鉄板などの買い目 "1-5-6"）との完全一致判定
                        if combo.strip() == winning_combo.strip():
                            is_hit = True
                            break

                        # ② フォーメーション出目（例: "3-145-1456"）の展開判定
                        parts = combo.replace("=", "-").split("-")
                        if len(parts) == 3:
                            head, r2_list, r3_list = parts[0], list(parts[1]), list(parts[2])
                            win_parts = winning_combo.split("-")
                            if len(win_parts) == 3 and (win_parts[0] in head and win_parts[1] in r2_list and win_parts[2] in r3_list):
                                is_hit = True
                                break

                    if is_hit:
                        is_manshu = payout >= 10000
                        print(f"    🎯 【的中 ({'万舟' if is_manshu else '通常'})】: {resolved_v} {rno}R ({payout:,}円)")
                        fields = [
                            {"name": "📍 対象レース", "value": f"{resolved_v} {rno}R"},
                            {"name": "🎲 確定出目", "value": f"3連単 {winning_combo}"},
                            {"name": "💰 払戻金", "value": f"{payout:,}円"},
                        ]

                        # ① 全的中ログチャンネルへ送信
                        send_discord_text(
                            webhook_url=ALL_RESULT_WEBHOOK_URL,
                            label="全的中ログ",
                            title=f"🎯【的中報告】 {resolved_v} {rno}R",
                            description=f"⚡ {alert_type} アラート配信のレースで見事的中しました！",
                            fields=fields,
                        )

                        # ② 万舟（10,000円以上）の場合のみ、万舟速報チャンネルへ送信（IFTTTが拾ってXへ投稿）
                        if is_manshu:
                            send_discord_text(
                                webhook_url=RESULT_WEBHOOK_URL,
                                label="万舟速報",
                                title=f"🎆【万舟的中！】 {resolved_v} {rno}R",
                                description=f"⚡ {alert_type} アラート配信のレースで見事万舟的中しました！",
                                fields=fields,
                            )
                    else:
                        print(f"    💀 【不的中】 推奨: {recommended_combos} / 結果: {winning_combo}")

                    del updated_pending[race_key]
                else:
                    print(f"    ⏳ 未確定/取得待ち: {resolved_v} {rno}R")

            try:
                with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(updated_pending, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 保存エラー: {e}")

if __name__ == "__main__":
    check_all_results()
