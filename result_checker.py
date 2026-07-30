import json
import os
import re
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=+9), "JST")

RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL")
PENDING_RESULTS_FILE = "pending_results.json"
PENDING_PICKUPS_FILE = "pending_pickup_races.json"

VENUE_NO_MAP = {
    "桐生": 1,   "戸田": 2,   "江戸川": 3, "平和島": 4, "多摩川": 5,
    "浜名湖": 6, "蒲郡": 7,   "常滑": 8,   "津": 9,     "三国": 10,
    "びわこ": 11, "住之江": 12, "尼崎": 13, "鳴門": 14, "丸亀": 15,
    "児島": 16,  "宮島": 17,  "徳山": 18, "下関": 19, "若松": 20,
    "芦屋": 21,  "福岡": 22,  "唐津": 23, "大村": 24,
}

SLUG_VENUE_MAP = {
    "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川", "heiwajima": "平和島",
    "tamagawa": "多摩川", "hamanako": "浜名湖", "gamagori": "蒲郡", "tokoname": "常滑",
    "tsu": "津", "mikuni": "三国", "biwako": "びわこ", "suminoe": "住之江",
    "amagasaki": "尼崎", "naruto": "鳴門", "marugame": "丸亀", "kojima": "児島",
    "miyajima": "宮島", "tokuyama": "徳山", "shimonoseki": "下関", "wakamatsu": "若松",
    "ashiya": "芦屋", "fukuoka": "福岡", "karatsu": "唐津", "omura": "大村"
}

def resolve_venue_name(raw_venue, clean_url="", race_key=""):
    cleaned = re.sub(r"\[.*?\]|joshi|[a-zA-Z\s]", "", str(raw_venue)).strip()
    if cleaned and cleaned in VENUE_NO_MAP:
        return cleaned

    if clean_url:
        for slug, jp_name in SLUG_VENUE_MAP.items():
            if slug in clean_url and slug != "joshi":
                return jp_name

    if race_key:
        for v in VENUE_NO_MAP.keys():
            if v in race_key:
                return v

    return ""

def send_discord_embed(webhook_url, title, description, fields=[], color=0x00FF00):
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

def fetch_official_result(venue_jp, rno, date_str=None, clean_url="", race_key=""):
    """ BOATRACE公式サイトからピンポイントで3連単の確定結果をパース """
    resolved_v = resolve_venue_name(venue_jp, clean_url, race_key)
    
    if resolved_v:
        candidate_venues = [resolved_v]
    else:
        candidate_venues = ["徳山", "三国", "常滑", "児島", "福岡", "唐津", "丸亀", "下関", "大村"]

    if not date_str or len(str(date_str)) < 8:
        raw_date = datetime.now(JST).strftime("%Y%m%d")
    else:
        raw_date = re.sub(r"\D", "", str(date_str))[:8]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    for v_name in candidate_venues:
        place_no = VENUE_NO_MAP.get(v_name)
        if not place_no:
            continue

        url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={place_no:02d}&hd={raw_date}"

        try:
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            
            # 「3連単」セルを直接特定
            target_cell = None
            for cell in soup.find_all(["td", "th"]):
                if cell.get_text(strip=True) == "3連単":
                    target_cell = cell
                    break

            if target_cell:
                # 親の <tr> または所属テーブルブロックを取得
                parent_tr = target_cell.find_parent("tr")
                if parent_tr:
                    # その行（および直後行）のテキストを全結合
                    tr_group_text = parent_tr.get_text(separator=" ", strip=True)
                    
                    # 組み合わせ (例: 1-2-3)
                    combo_m = re.search(r"([1-6])\s*[-–—─=⇒>→]\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6])", tr_group_text)
                    # 金額
                    payout_m = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})", tr_group_text)

                    if combo_m and payout_m:
                        combo = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                        for p_str in reversed(payout_m):
                            val = int(p_str.replace(",", ""))
                            if 100 <= val <= 999999:
                                return combo, val, v_name

        except Exception:
            pass

    return None, 0, resolved_v

def check_all_results():
    if not os.path.exists(PENDING_RESULTS_FILE) and not os.path.exists(PENDING_PICKUPS_FILE):
        print("☕ 追跡対象のデータが存在しません。")
        return

    today_str = datetime.now(JST).strftime("%Y%m%d")

    if os.path.exists(PENDING_RESULTS_FILE):
        with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
            pending_results = json.load(f)

        if pending_results:
            updated_pending = {}
            for k, v in pending_results.items():
                d = str(v.get("date") or v.get("d") or "").replace("-", "").replace("/", "")[:8]
                if not d or d == today_str:
                    updated_pending[k] = v
                else:
                    print(f"🗑️ 古いアラートデータを削除: {k} (日付: {d})")

            print(f"🔍 追跡中アラート ({len(updated_pending)}件) の結果照会を開始...")

            for race_key, info in list(updated_pending.items()):
                rno = info.get("rno")
                raw_venue_jp = info.get("venue_jp") or info.get("venue") or info.get("v") or ""
                clean_url = info.get("clean_url", "")
                date_str = info.get("date") or info.get("d")
                alert_type = info.get("alert_type")
                recommended_combos = info.get("recommended_combos", [])

                winning_combo, payout, resolved_v = fetch_official_result(raw_venue_jp, rno, date_str, clean_url, race_key)
                display_venue = resolved_v if resolved_v else raw_venue_jp

                if winning_combo:
                    print(f"   🏁 結果取得成功: {display_venue} {rno}R -> 3連単 {winning_combo} ({payout:,}円)")
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
                        print(f"   🎯 【的中】 Discord通知送信: {display_venue} {rno}R")
                        send_discord_embed(
                            webhook_url=RESULT_WEBHOOK_URL,
                            title=f"🎯【AIアラート的中報告】 {display_venue} {rno}R",
                            description=f"⚡ **{alert_type}** アラート配信のレースで見事的中しました！",
                            fields=[
                                {"name": "📍 対象レース", "value": f"{display_venue} {rno}R", "inline": True},
                                {"name": "🎲 確定出目", "value": f"**3連単 {winning_combo}**", "inline": True},
                                {"name": "💰 払戻金", "value": f"**{payout:,}円**", "inline": True},
                            ],
                            color=0x00FF00,
                        )
                    else:
                        print(f"   💀 【不的中】 推奨: {recommended_combos} / 結果: {winning_combo}")

                    del updated_pending[race_key]
                else:
                    print(f"   ⏳ 未確定/取得待ち: {display_venue} {rno}R")

            with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(updated_pending, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    check_all_results()
