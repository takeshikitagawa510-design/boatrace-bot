import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import requests

JST = timezone(timedelta(hours=+9), "JST")

RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL")
PENDING_RESULTS_FILE = "pending_results.json"
PENDING_PICKUPS_FILE = "pending_pickup_races.json"

VENUE_NO_MAP = {
    "桐生": 1, "戸田": 2, "江戸川": 3, "平和島": 4, "多摩川": 5,
    "浜名湖": 6, "蒲郡": 7, "常滑": 8, "津": 9, "びわこ": 10,
    "住之江": 11, "尼崎": 12, "鳴門": 13, "丸亀": 14, "児島": 15,
    "宮島": 16, "徳山": 17, "下関": 18, "若松": 19, "芦屋": 20,
    "福岡": 21, "唐津": 22, "大村": 23, "三国": 24,
}

def clean_venue_name(raw_name):
    if not raw_name: return ""
    return re.sub(r"\[.*?\]|joshi|[a-zA-Z\s]", "", str(raw_name)).strip()

def fetch_kyoteibiyori_sanrentan_result(venue_jp, rno, date_str=None):
    clean_v = clean_venue_name(venue_jp)
    place_no = VENUE_NO_MAP.get(clean_v)
    if not place_no:
        print(f"⚠️ 未対応の会場名: '{venue_jp}'")
        return None, 0

    if not date_str or len(str(date_str)) < 8:
        date_str = datetime.now(JST).strftime("%Y%m%d")
    else:
        date_str = str(date_str).replace("-", "").replace("/", "")[:8]

    url = f"https://kyoteibiyori.com/race_result_all.php?place_no={place_no}&hiduke={date_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        print(f"DEBUG: [{clean_v} {rno}R] HTTP Response Code: {resp.status_code}, Length: {len(resp.text)}")
        
        # もしHTMLが短すぎる場合、ブロックされているか動的描画ページ
        if len(resp.text) < 2000:
            print(f"⚠️ レスポンス本文が短すぎます（ブロックまたはJS描画の可能性）:\n{resp.text[:300]}")
            return None, 0

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 3連単の検索
        target_r = f"{rno}R"
        for table in soup.find_all("table"):
            t_text = table.get_text()
            if target_r in t_text and ("3連単" in t_text or "三連単" in t_text):
                combo_m = re.search(r"([1-6])\s*[-–—─=⇒>]\s*([1-6])\s*[-–—─=⇒>]\s*([1-6])", t_text)
                payout_m = re.search(r"([0-9,]+)\s*円", t_text)
                if combo_m and payout_m:
                    payout_val = int(payout_m.group(1).replace(",", ""))
                    if payout_val > 0:
                        return f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}", payout_val

    except Exception as e:
        print(f"⚠️ 通信/解析例外: {e}")

    return None, 0

def check_realtime_results():
    if not os.path.exists(PENDING_RESULTS_FILE): return
    with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
        pending_results = json.load(f)
    if not pending_results: return

    print(f"🔍 追跡中アラート ({len(pending_results)}件) の結果照会を開始...")
    for race_key, info in list(pending_results.items()):
        rno = info.get("rno")
        venue_jp = clean_venue_name(info.get("venue_jp") or info.get("venue") or info.get("v") or "")
        date_str = info.get("date") or info.get("d")
        if not venue_jp or not rno: continue

        winning_combo, payout = fetch_kyoteibiyori_sanrentan_result(venue_jp, rno, date_str=date_str)
        if winning_combo:
            print(f"   🏁 結果取得成功: {venue_jp} {rno}R -> {winning_combo} ({payout}円)")
        else:
            print(f"   ⏳ 取得失敗/未確定: {venue_jp} {rno}R")

if __name__ == "__main__":
    check_realtime_results()
