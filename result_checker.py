import json
import os
import re
import ssl
import time
import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.poolmanager import PoolManager
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=+9), "JST")

# 既存のWebhook（IFTTTが監視しているチャンネル：万舟のみ送信）
RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL", "").strip()
# 新設のWebhook（全的中を記録するチャンネル）
ALL_RESULT_WEBHOOK_URL = os.environ.get("ALL_RESULT_DISCORD_WEBHOOK_URL", "").strip()

SHINSUM_USER = os.environ.get("SHINSUM_USER") or "sum"
SHINSUM_PASS = os.environ.get("SHINSUM_PASS") or "sao"

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

# ==========================================
# 🔒 TLSフィンガープリント対策用アダプター
# ==========================================
class BrowserTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS")
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx,
        )

def get_browser_session():
    s = requests.Session()
    s.mount("https://", BrowserTLSAdapter())
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    })
    return s

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

def parse_trifecta_from_html(html_text):
    soup = BeautifulSoup(html_text, "html.parser")

    # ① テーブル行（tr）から「3連単」行を抽出
    for tr in soup.find_all("tr"):
        tr_text = tr.get_text(separator=" ", strip=True)
        if "3連単" in tr_text:
            combo_m = re.search(r"([1-6])\s*[-–—─=⇒>→]\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6])", tr_text)
            yen_m = re.search(r"[¥￥]\s*([0-9,]{3,8})", tr_text)
            if combo_m and yen_m:
                combo = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                val = int(yen_m.group(1).replace(",", ""))
                if val >= 100:
                    return combo, val

            payout_m = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,7})", tr_text)
            if combo_m and payout_m:
                combo = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                valid_vals = [int(x.replace(",", "")) for x in payout_m if int(x.replace(",", "")) >= 100]
                if valid_vals:
                    return combo, valid_vals[0]

    # ② 全体テキストからのフォールバック検索
    text_all = soup.get_text(separator=" ", strip=True)
    match = re.search(
        r"3連単\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6]).{0,40}?(?:[¥￥]\s*([0-9,]{3,8})|([0-9,]{3,8})\s*円)",
        text_all
    )
    if match:
        combo = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        raw_val = match.group(4) or match.group(5)
        payout_val = int(raw_val.replace(",", ""))
        if payout_val >= 100:
            return combo, payout_val

    return None, 0

# ==========================================
# 🌐 3段階マルチソース結果取得エンジン
# ==========================================
def fetch_official_result(venue_jp, rno, date_str=None, clean_url="", race_key=""):
    resolved_v = resolve_venue_name(venue_jp, clean_url, race_key)
    if not resolved_v:
        return None, 0, ""

    place_no = VENUE_NO_MAP.get(resolved_v)
    if not place_no:
        return None, 0, resolved_v

    if not date_str or len(str(date_str)) < 8:
        raw_date = datetime.now(JST).strftime("%Y%m%d")
    else:
        raw_date = re.sub(r"\D", "", str(date_str))[:8]

    session = get_browser_session()

    # --------------------------------------------------
    # ルート1: boatrace.jp（TLSカスタム＋モバイル版エンドポイント）
    # --------------------------------------------------
    candidate_urls = [
        f"https://www.boatrace.jp/owsp/sp/race/raceresult?rno={rno}&jcd={place_no:02d}&hd={raw_date}",
        f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={place_no:02d}&hd={raw_date}",
    ]
    for url in candidate_urls:
        try:
            res = session.get(url, timeout=8)
            if res.status_code == 200 and len(res.text) > 1000:
                res.encoding = "utf-8"
                combo, val = parse_trifecta_from_html(res.text)
                if combo:
                    return combo, val, resolved_v
        except Exception:
            pass

    # --------------------------------------------------
    # ルート2: 競艇日和（kyoteibiyori.com）当日結果ページ
    # --------------------------------------------------
    try:
        biyori_url = f"https://kyoteibiyori.com/race_shusso.php?place_no={place_no}&race_no={rno}&hiduke={raw_date}&slider=4"
        res_b = session.get(biyori_url, timeout=8)
        if res_b.status_code == 200 and len(res_b.text) > 1000:
            res_b.encoding = "utf-8"
            combo, val = parse_trifecta_from_html(res_b.text)
            if combo:
                return combo, val, resolved_v
    except Exception:
        pass

    # --------------------------------------------------
    # ルート3: 艇国データバンク（boatrace-db.net）当日結果ページ
    # --------------------------------------------------
    try:
        db_url = f"https://boatrace-db.net/race/result/pid/{place_no:02d}/date/{raw_date}/rno/{rno}/"
        res_db = session.get(db_url, timeout=8)
        if res_db.status_code == 200 and len(res_db.text) > 1000:
            res_db.encoding = "utf-8"
            combo, val = parse_trifecta_from_html(res_db.text)
            if combo:
                return combo, val, resolved_v
    except Exception:
        pass

    return None, 0, resolved_v

def check_all_results():
    print(f"🔧 Webhook確認 -> ALL_RESULT: {'設定済' if ALL_RESULT_WEBHOOK_URL else '未設定'} / MANSHU(RESULT): {'設定済' if RESULT_WEBHOOK_URL else '未設定'}")

    if not os.path.exists(PENDING_RESULTS_FILE) and not os.path.exists(PENDING_PICKUPS_FILE):
        print("☕ 追跡対象のデータが存在しません。")
        return

    today_str = datetime.now(JST).strftime("%Y%m%d")

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
                alert_type = info.get("alert_type", "AIアラート")
                recommended_combos = info.get("recommended_combos", [])

                resolved_v = resolve_venue_name(raw_venue_jp, clean_url, race_key)
                if not resolved_v:
                    print(f"    ⚠️ 会場不明のためスキップ: {raw_venue_jp} {rno}R (key: {race_key})")
                    continue

                winning_combo, payout, display_venue = fetch_official_result(
                    raw_venue_jp, rno, date_str, clean_url, race_key
                )

                if winning_combo:
                    print(f"    🏁 結果取得成功: {display_venue} {rno}R -> 確定: {winning_combo} ({payout:,}円) | 推奨: {recommended_combos}")
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
                        print(f"    🎯 【的中 ({'万舟' if is_manshu else '通常'})】: {display_venue} {rno}R ({payout:,}円)")
                        
                        fields = [
                            {"name": "📍 対象レース", "value": f"{display_venue} {rno}R"},
                            {"name": "🎲 確定出目", "value": f"3連単 {winning_combo}"},
                            {"name": "💰 払戻金", "value": f"{payout:,}円"},
                        ]

                        # ① 全的中ログチャンネルへ送信（通常・鉄板すべての的中）
                        send_discord_text(
                            webhook_url=ALL_RESULT_WEBHOOK_URL,
                            label="全的中ログ",
                            title=f"🎯【的中報告】 {display_venue} {rno}R",
                            description=f"⚡ {alert_type} アラート配信のレースで見事的中しました！",
                            fields=fields,
                        )

                        # ② 万舟（10,000円以上）の場合のみ、既存チャンネルへ送信（IFTTTが拾ってXへ投稿）
                        if is_manshu:
                            send_discord_text(
                                webhook_url=RESULT_WEBHOOK_URL,
                                label="万舟速報",
                                title=f"🎆【万舟的中！】 {display_venue} {rno}R",
                                description=f"⚡ {alert_type} アラート配信のレースで見事万舟的中しました！",
                                fields=fields,
                            )
                    else:
                        print(f"    💀 【不的中】 推奨: {recommended_combos} / 結果: {winning_combo}")

                    del updated_pending[race_key]
                else:
                    print(f"    ⏳ 未確定/取得待ち: {display_venue} {rno}R")

            try:
                with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(updated_pending, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"⚠️ 保存エラー: {e}")

if __name__ == "__main__":
    check_all_results()
