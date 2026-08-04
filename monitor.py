import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from requests.auth import HTTPBasicAuth

# ==========================================
# 🎯 1. 初期設定
# ==========================================
DATA_URL = "https://boatrace-shinsum.com/"
CHECKER_URL = "https://boatrace-shinsum.com/checker/shinsum_checker.json"

USER_ID = os.environ.get("SHINSUM_USER") or "sum"
PASSWORD = os.environ.get("SHINSUM_PASS") or "pom"

# ⚡ リアルタイム監視用 Webhook（カードのみ送信）
DISCORD_WEBHOOK_URL = os.environ.get("MONITOR_DISCORD_WEBHOOK_URL")

# 🎯 的中・回収実績用 Webhook（テキストのみ送信）
RESULT_DISCORD_WEBHOOK_URL = os.environ.get(
    "RESULT_DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1531249075117096990/URp3Tock98zsni_jSoH2qCvepmsRoYo2sWLyV7_XcuaPYyQxGvwIKcKUeWTUWfsjOkLZ"
)

CACHE_FILE = "notified_races.json"
PENDING_RESULTS_FILE = "pending_results.json"
PENDING_PICKUP_FILE = "pending_pickup_races.json"

JST = timezone(timedelta(hours=+9), "JST")
TODAY_STR = datetime.now(JST).strftime("%Y%m%d")  # 本日の日付 (例: 20260801)

# 💡 tamakawa, tamagawa 双方を「多摩川 (5)」として判定できるよう設定
VENUE_NO_MAP = {
    "桐生": 1,   "戸田": 2,   "江戸川": 3, "平和島": 4, "多摩川": 5, "tamagawa": 5, "tamakawa": 5,
    "浜名湖": 6, "蒲郡": 7,   "常滑": 8,   "津": 9,     "三国": 10,
    "びわこ": 11, "住之江": 12, "尼崎": 13, "鳴門": 14, "丸亀": 15,
    "児島": 16,  "宮島": 17,  "徳山": 18, "下関": 19, "若松": 20,
    "芦屋": 21,  "福岡": 22,  "唐津": 23, "大村": 24,
}

notified_races = set()
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            raw_notified = json.load(f)
            notified_races = {k for k in raw_notified if k.startswith(TODAY_STR)}
        print(f"📦 本日 ({TODAY_STR}) の通知済みキャッシュ ({len(notified_races)}件) を読み込みました。")
    except Exception as e:
        print(f"⚠️ キャッシュ読み込みエラー: {e}")

def save_notified_races():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(notified_races), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ キャッシュ保存エラー: {e}")

today_venues = set()
checker_data = {}

AUTH = HTTPBasicAuth(USER_ID, PASSWORD)

session = requests.Session()
session.auth = AUTH
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
})

# 💡 リアルタイム監視用：カード（Embed）のみ送信（content なし）
def send_discord_embed(webhook_url, title, description, fields=[], color=0x00FFFF):
    if not webhook_url:
        print(f"⚠️ Webhook URL未設定のためスキップ: {title}")
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
        print(f"📡 Discordリアルタイム送信結果 (カードのみ): HTTP {res.status_code}")
    except Exception as e:
        print(f"⚠️ Discord通信エラー: {e}")

# 💡 的中・回収実績用：テキストのみ送信（embeds 一切なし）
def send_discord_text(webhook_url, title, description, fields=[]):
    if not webhook_url:
        print(f"⚠️ Webhook URL未設定のためスキップ: {title}")
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
    )

    # embeds キーを含めず、content のみ送信する
    payload = {
        "content": plain_content
    }
    
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📡 Discord実績送信結果 (テキストのみ): HTTP {res.status_code}")
    except Exception as e:
        print(f"⚠️ Discord通信エラー: {e}")

def perform_login():
    try:
        resp = session.get(DATA_URL, auth=AUTH, timeout=10)
        if resp.status_code == 200:
            print("🔑 Basic認証成功 (Status Code: 200)")
        else:
            print(f"⚠️ 認証応答コード: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ 通信エラー: {e}")

def update_venues():
    global today_venues
    try:
        resp = session.get(DATA_URL, auth=AUTH, timeout=10)
        if resp.status_code == 401:
            print("⚠️ 認証エラー: ID/PASSWORDを確認してください。")
            return

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        base_clean_url = DATA_URL.rstrip("/")

        for a in soup.find_all("a"):
            href = a.get("href")
            if not href or any(
                skip in href for skip in ["login", "logout", "wp-", "/checker/", "#", "javascript:"]
            ):
                continue

            full_url = urljoin(DATA_URL, href)
            if "boatrace-shinsum.com" in full_url:
                clean_url = full_url.split("?")[0].rstrip("/")
                if clean_url and clean_url != base_clean_url:
                    today_venues.add(clean_url + "/")

        fallback_venues = [
            "https://boatrace-shinsum.com/omura/",
            "https://boatrace-shinsum.com/joshi/omura/",
            "https://boatrace-shinsum.com/omura_sg/",
            "https://boatrace-shinsum.com/wakamatsu/",
            "https://boatrace-shinsum.com/marugame/",
            "https://boatrace-shinsum.com/suminoe/",
            "https://boatrace-shinsum.com/shimonoseki/",
            "https://boatrace-shinsum.com/kiryu/",
            "https://boatrace-shinsum.com/gamagori/",
        ]
        for fv in fallback_venues:
            today_venues.add(fv)

        print(f"✅ 巡回対象の会場URL ({len(today_venues)}件)")

    except Exception as e:
        print(f"⚠️ 会場更新エラー: {e}")

# ==========================================
# 📊 2. AI確率解析ロジック
# ==========================================
def load_checker_data():
    global checker_data
    try:
        timestamp = int(time.time() * 1000)
        resp = session.get(f"{CHECKER_URL}?t={timestamp}", auth=AUTH, timeout=10)
        if resp.status_code == 401:
            perform_login()
            resp = session.get(f"{CHECKER_URL}?t={timestamp}", auth=AUTH, timeout=10)

        if resp.status_code == 200:
            checker_data = resp.json()
            print(f"✅ チェッカーデータ読み込み完了")
    except Exception as e:
        print(f"⚠️ データロードエラー: {e}")

def get_real_probabilities(toban, waku, time_diff_val):
    if not checker_data or not toban or str(toban) not in checker_data:
        return None
    player_waku_data = next(
        (w for w in checker_data[str(toban)] if w.get("n") == waku), None
    )
    if not player_waku_data:
        return None

    target_range = (
        "大プラス" if time_diff_val >= 0.5
        else ("小プラス" if time_diff_val >= 0.0
        else "小マイナス" if time_diff_val >= -0.5 else "大マイナス")
    )
    for row in player_waku_data.get("rows", []):
        if row.get("name") == target_range:
            return {
                "r1": float(row.get("r1", 0.0)),
                "r2": float(row.get("r2", 0.0)),
                "r3": float(row.get("r3", 0.0)),
            }
    return {
        "r1": float(player_waku_data.get("t1", 0.0)),
        "r2": float(player_waku_data.get("t2", 0.0)),
        "r3": float(player_waku_data.get("t3", 0.0)),
    }

def generate_probability_eye(boats):
    if not isinstance(boats, list) or len(boats) < 6:
        return "データ不足により算出不可", "対象なし"

    analyzed_boats = []
    has_valid_checker = False

    for i, b in enumerate(boats):
        waku = i + 1
        b_str = json.dumps(b, ensure_ascii=False)

        toban = None
        for exact_key in ["id", "no", "toban", "register_id", "player_id", "touban"]:
            if exact_key in b and str(b[exact_key]).isdigit() and 3000 <= int(b[exact_key]) <= 6000:
                toban = b[exact_key]
                break
        if not toban:
            for k, v in b.items():
                if str(v).isdigit() and 3000 <= int(v) <= 6000:
                    toban = v
                    break

        time_diff_val = 0.0
        for cand in ["+0.", "＋0.", "-0.", "－0.", "−0."]:
            if cand in b_str:
                try:
                    start_idx = b_str.find(cand)
                    sub_str = (
                        b_str[start_idx : start_idx + 5]
                        .replace("＋", "+")
                        .replace("－", "-")
                        .replace("−", "-")
                    )
                    time_diff_val = float("".join(c for c in sub_str if c in "+-.0123456789"))
                    break
                except:
                    pass

        is_alert_target = ("Imperial" in b_str or "覚醒" in b_str) and ("+" in b_str or "＋" in b_str)

        probs = get_real_probabilities(toban, waku, time_diff_val)
        if probs:
            has_valid_checker = True
            analyzed_boats.append({
                "waku": waku, "r1": probs["r1"], "r2": probs["r2"], "r3": probs["r3"],
                "is_alert": is_alert_target, "tdiff": time_diff_val,
            })
        else:
            analyzed_boats.append({
                "waku": waku, "r1": 0.0, "r2": 0.0, "r3": 0.0,
                "is_alert": is_alert_target, "tdiff": time_diff_val,
            })

    if has_valid_checker:
        pool_2to6 = analyzed_boats[1:]
        main_head = max(pool_2to6, key=lambda x: x["r1"])

        other_boats = [b for b in analyzed_boats if b["waku"] != main_head["waku"]]
        top_r2_boats = sorted(other_boats, key=lambda x: x["r2"], reverse=True)[:3]
        top_r3_boats = sorted(other_boats, key=lambda x: x["r3"], reverse=True)[:3]

        r2_str = "".join(str(b["waku"]) for b in top_r2_boats)
        r3_str = "".join(str(b["waku"]) for b in top_r3_boats)
        main_eye = f"{main_head['waku']}-{r2_str}-{r3_str}"

        sub_pool = [b for b in analyzed_boats if b["waku"] > main_head["waku"]]
        sub_eye = "対象なし"
        if sub_pool:
            sub_head = max(sub_pool, key=lambda x: x["r1"])
            sub_others = [b for b in analyzed_boats if b["waku"] != sub_head["waku"]]
            sub_r2_boats = sorted(sub_others, key=lambda x: x["r2"], reverse=True)[:3]
            sub_r3_boats = sorted(sub_others, key=lambda x: x["r3"], reverse=True)[:3]
            sub_r2_str = "".join(str(b["waku"]) for b in sub_r2_boats)
            sub_r3_str = "".join(str(b["waku"]) for b in sub_r3_boats)
            sub_eye = f"{sub_head['waku']}-{sub_r2_str}-{sub_r3_str}"

        return main_eye, sub_eye
    else:
        pool_2to6 = [b for b in analyzed_boats[1:] if b["is_alert"]]
        if not pool_2to6:
            pool_2to6 = analyzed_boats[1:]

        main_head = max(pool_2to6, key=lambda x: x["tdiff"])
        other_boats = sorted(
            [b for b in analyzed_boats if b["waku"] != main_head["waku"]],
            key=lambda x: x["tdiff"], reverse=True,
        )
        r2_str = "".join(str(b["waku"]) for b in other_boats[:3])
        r3_str = "".join(str(b["waku"]) for b in other_boats[:4])
        main_eye = f"{main_head['waku']}-{r2_str}-{r3_str}"

        sub_pool = [b for b in analyzed_boats if b["waku"] > main_head["waku"]]
        sub_eye = "対象なし"
        if sub_pool:
            sub_head = max(sub_pool, key=lambda x: x["tdiff"])
            sub_others = sorted(
                [b for b in analyzed_boats if b["waku"] != sub_head["waku"]],
                key=lambda x: x["tdiff"], reverse=True,
            )
            sub_r2_str = "".join(str(b["waku"]) for b in sub_others[:3])
            sub_r3_str = "".join(str(b["waku"]) for b in sub_others[:4])
            sub_eye = f"{sub_head['waku']}-{sub_r2_str}-{sub_r3_str}"

        return main_eye, sub_eye

# ==========================================
# 💰 4. 万舟ピックアップ結果照会ロジック
# ==========================================
def fetch_official_result_simple(venue_jp, rno, date_str):
    """ BOATRACE公式サイトから指定レースの3連単結果と払戻金を取得 """
    place_no = VENUE_NO_MAP.get(venue_jp)
    if not place_no:
        return None, 0

    raw_date = re.sub(r"\D", "", str(date_str))[:8]
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={place_no:02d}&hd={raw_date}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.boatrace.jp/"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None, 0

        soup = BeautifulSoup(res.text, "html.parser")
        text_all = soup.get_text(separator=" ", strip=True)

        match = re.search(r"3連単\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6])\s*(?:¥|￥)?\s*([0-9,]{3,7})", text_all)
        if match:
            combo = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            payout_val = int(match.group(4).replace(",", ""))
            return combo, payout_val

        for tr in soup.find_all("tr"):
            tr_text = tr.get_text(separator=" ", strip=True)
            if "3連単" in tr_text:
                combo_m = re.search(r"([1-6])\s*[-–—─=⇒>→]\s*([1-6])\s*[-–—─=⇒>→]\s*([1-6])", tr_text)
                payout_m = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,6})", tr_text)
                if combo_m and payout_m:
                    combo = f"{combo_m.group(1)}-{combo_m.group(2)}-{combo_m.group(3)}"
                    val = int(payout_m[-1].replace(",", ""))
                    if val >= 100:
                        return combo, val
    except Exception:
        pass

    return None, 0

def check_pickup_manshu_results():
    """ pending_pickup_races.json のレース結果を追跡し、万舟(1万円以上)だった場合🎯｜ai的中・回収実績 へ通知 """
    if not os.path.exists(PENDING_PICKUP_FILE):
        return

    try:
        with open(PENDING_PICKUP_FILE, "r", encoding="utf-8") as f:
            pickups = json.load(f)
    except Exception:
        return

    if not pickups:
        return

    print(f"💣 万舟ピックアップレース ({len(pickups)}件) の結果照会を開始...")
    updated_pickups = dict(pickups)

    for race_key, info in list(pickups.items()):
        v_name = info.get("v", "")
        rno = info.get("r", 0)
        score = info.get("s", 0)
        date_str = info.get("date", TODAY_STR)

        winning_combo, payout = fetch_official_result_simple(v_name, rno, date_str)

        if winning_combo:
            print(f"    📊 ピックアップ結果: {v_name} {rno}R (Score: {score}) -> 3連単 {winning_combo} ({payout:,}円)")
            
            # 💰 的中・回収実績は「プレーンテキストのみ (send_discord_text)」で送信
            if payout >= 10000:
                print(f"    🎆 【万舟発生】 🎯｜ai的中・回収実績 へ送信: {v_name} {rno}R ({payout:,}円)")
                fields = [
                    {"name": "📍 対象レース", "value": f"{v_name} {rno}R"},
                    {"name": "🎲 確定出目", "value": f"3連単 {winning_combo}"},
                    {"name": "💰 払戻金", "value": f"{payout:,}円"},
                ]
                send_discord_text(
                    webhook_url=RESULT_DISCORD_WEBHOOK_URL,
                    title=f"🎆【万舟的中・回収実績】ピックアップレース {v_name} {rno}R",
                    description=f"🔥 AI期待値スコア {score}点 の注目レースで見事万舟（{payout:,}円）が飛び出しました！",
                    fields=fields,
                )

            del updated_pickups[race_key]
        else:
            print(f"    ⏳ ピックアップ未確定: {v_name} {rno}R")

    try:
        with open(PENDING_PICKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_pickups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_PICKUP_FILE} 保存エラー: {e}")

# ==========================================
# 🚀 3. リアルタイムAI監視ロジック
# ==========================================
def monitor_shinsum(venue_urls):
    global notified_races
    venue_name_map = {
        "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川", "tokoname": "常滑",
        "mikuni": "三国", "marugame": "丸亀", "miyajima": "宮島", "tokuyama": "徳山",
        "ashiya": "芦屋", "omura": "大村", "omura_sg": "大村", "gamagori": "蒲郡",
        "hamanako_sg": "浜名湖", "hamanako": "浜名湖", "heiwajima": "平和島",
        "tamagawa": "多摩川", "tamakawa": "多摩川", "tsu": "津", "biwako": "びわこ", "suminoe": "住之江",
        "amagasaki": "尼崎", "naruto": "鳴門", "karatsu": "唐津", "kojima": "児島",
        "wakamatsu": "若松", "fukuoka": "福岡", "shimonoseki": "下関",
    }

    pending_results = {}
    if os.path.exists(PENDING_RESULTS_FILE):
        try:
            with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
                pending_results = json.load(f)
        except Exception:
            pending_results = {}

    for venue_url in venue_urls:
        parsed = urlparse(venue_url)
        base_path = parsed.path.split('?')[0].rstrip("/")
        clean_base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"

        path_parts = [p for p in base_path.split("/") if p]
        venue_id_name = next((p for p in reversed(path_parts) if p != "joshi"), "")
        is_joshi = "joshi" in path_parts

        pure_venue = venue_name_map.get(venue_id_name, venue_id_name)

        # 💡 【追加】"boatrace" や空文字の場合のみ「住之江」に自動変換
        if pure_venue in ["boatrace", ""]:
            pure_venue = "住之江"

        venue_japanese = f"[女子]{pure_venue}" if is_joshi else pure_venue

        timestamp = int(time.time() * 1000)
        shinsum_data, arare_data = {}, {}

        try:
            s_resp = session.get(f"{clean_base_url}/shinsum.json?t={timestamp}", auth=AUTH, timeout=8)
            if s_resp.status_code == 200:
                shinsum_data = s_resp.json()
            elif s_resp.status_code == 401:
                perform_login()
        except Exception as e:
            print(f"⚠️ {venue_japanese} shinsum.json 取得エラー: {e}")

        try:
            a_resp = session.get(f"{clean_base_url}/arare.json?t={timestamp}", auth=AUTH, timeout=8)
            if a_resp.status_code == 200:
                arare_data = a_resp.json()
        except Exception as e:
            print(f"⚠️ {venue_japanese} arare.json 取得エラー: {e}")

        # 💡 データ内の日付チェック
        data_date = None
        for check_d in [shinsum_data, arare_data]:
            if isinstance(check_d, dict):
                date_val = check_d.get("date") or check_d.get("created_at") or ""
                clean_d = re.sub(r"\D", "", str(date_val))[:8]
                if len(clean_d) == 8:
                    data_date = clean_d
                    break

        if data_date and data_date != TODAY_STR:
            print(f"⏭️ 【スキップ】{venue_japanese} は過去の日付データです ({data_date} != {TODAY_STR})")
            continue

        all_race_keys = set(shinsum_data.keys()) | set(arare_data.keys())

        for rno_key in all_race_keys:
            try:
                rno_str = str(int(rno_key.replace("R", "")))
            except ValueError:
                continue

            slit_race_id = f"{TODAY_STR}_{venue_japanese}_{rno_str}_slit"
            rate_race_id = f"{TODAY_STR}_{venue_japanese}_{rno_str}_rate"
            kakusei_race_id = f"{TODAY_STR}_{venue_japanese}_{rno_str}_kakusei"

            boats = (
                shinsum_data.get(rno_key, {}).get("boats", [])
                or arare_data.get(rno_key, {}).get("boats", [])
            )
            if not boats:
                continue

            # ① 覚醒タイム（カードのみ送信）
            if kakusei_race_id not in notified_races:
                kakusei_alerts = []
                is_triggered = False
                if isinstance(boats, list):
                    for i, b in enumerate(boats):
                        teiban = i + 1
                        b_str = json.dumps(b, ensure_ascii=False)
                        if ("Imperial" in b_str or "覚醒" in b_str) and ("+" in b_str or "＋" in b_str):
                            is_triggered = True
                            type_label = "🔥MAX覚醒" if "Imperial" in b_str else "🌟機力覚醒"
                            kakusei_alerts.append(f"{teiban}枠({type_label})")
                if is_triggered:
                    main_eye, sub_eye = generate_probability_eye(boats)
                    fields = [
                        {"name": "🎯 メイン穴目", "value": f"`{main_eye}`", "inline": True},
                        {"name": "🔮 外枠サブ目", "value": f"`{sub_eye}`", "inline": True},
                        {"name": "⚡ 該当艇", "value": ", ".join(kakusei_alerts), "inline": False},
                    ]
                    send_discord_embed(
                        webhook_url=DISCORD_WEBHOOK_URL,
                        title=f"🚨 機力覚醒シグナル検知！ 【{venue_japanese} {rno_str}R】",
                        description="対象艇の舟足・機力が大幅覚醒！高配当ターゲットレースです。",
                        fields=fields,
                        color=0xFF0055,
                    )
                    notified_races.add(kakusei_race_id)
                    save_notified_races()

                    pending_results[kakusei_race_id] = {
                        "clean_url": clean_base_url,
                        "rno": int(rno_str),
                        "venue_jp": pure_venue,
                        "date": TODAY_STR,
                        "alert_type": "機力覚醒シグナル",
                        "recommended_combos": [main_eye, sub_eye],
                    }

            # ② 勝率判定（カードのみ送信）
            if rate_race_id not in notified_races:
                w1_rate = None
                other_rates = []
                for i, b in enumerate(boats):
                    teiban = i + 1
                    shin_1chaku = b.get("rate_1")
                    if shin_1chaku is not None:
                        try:
                            clean_str = (
                                str(shin_1chaku)
                                .replace("%", "").replace("+", "").replace("＋", "")
                                .replace("－", "-").replace("−", "-").strip()
                            )
                            if clean_str:
                                diff = float(clean_str)
                                if teiban == 1:
                                    w1_rate = diff
                                elif 2 <= teiban <= 6:
                                    other_rates.append((diff, teiban))
                        except:
                            continue
                if other_rates:
                    other_max_val, other_max_waku = max(other_rates, key=lambda x: x[0])
                    is_chobatsu = other_max_val >= 10.0
                    is_in_tobi = w1_rate is not None and w1_rate < 0 and other_max_val >= 5.0

                    if is_chobatsu or is_in_tobi:
                        title = "🌟 超抜シグナル到来！" if is_chobatsu else "🔥 イン波乱警戒シグナル！"
                        w1_str = f"+{w1_rate}" if (w1_rate is not None and w1_rate > 0) else f"{w1_rate}" if w1_rate is not None else "不明"
                        other_str = f"+{other_max_val}" if other_max_val > 0 else f"{other_max_val}"

                        main_eye, sub_eye = generate_probability_eye(boats)

                        fields = [
                            {
                                "name": "📊 勝率データ",
                                "value": f"1枠: `{w1_str}%` ｜ 狙い目 `{other_max_waku}枠`: `{other_str}%`",
                                "inline": False,
                            },
                            {"name": "🎯 メイン穴目", "value": f"`{main_eye}`", "inline": True},
                            {"name": "🔮 外枠サブ目", "value": f"`{sub_eye}`", "inline": True},
                        ]
                        send_discord_embed(
                            webhook_url=DISCORD_WEBHOOK_URL,
                            title=f"{title} 【{venue_japanese} {rno_str}R】",
                            description="AI解析により勝率偏向データを検知しました。",
                            fields=fields,
                            color=0xFFD700 if is_chobatsu else 0xFF4500,
                        )
                        notified_races.add(rate_race_id)
                        save_notified_races()

                        pending_results[rate_race_id] = {
                            "clean_url": clean_base_url,
                            "rno": int(rno_str),
                            "venue_jp": pure_venue,
                            "date": TODAY_STR,
                            "alert_type": title,
                            "recommended_combos": [main_eye, sub_eye],
                        }

            # ③ スリットアラート（カードのみ送信）
            if slit_race_id not in notified_races:
                race_shinsum_str = json.dumps(shinsum_data.get(rno_key, {}), ensure_ascii=False)
                race_arare_str = json.dumps(arare_data.get(rno_key, {}), ensure_ascii=False)
                combined_race_text = race_shinsum_str + race_arare_str
                if "+" in combined_race_text or "＋" in combined_race_text:
                    slit_msg_details = []
                    if isinstance(boats, list):
                        for i, b in enumerate(boats):
                            teiban = i + 1
                            b_str = json.dumps(b, ensure_ascii=False)
                            if "+" in b_str or "＋" in b_str:
                                val = "確認"
                                for cand in ["+0.1", "+0.2", "+0.3", "＋0.1", "＋0.2", "＋0.3"]:
                                    if cand in b_str:
                                        val = cand.replace("＋", "+")
                                        break
                                slit_msg_details.append(f"{teiban}枠: {val}")
                    if not slit_msg_details:
                        slit_msg_details.append("展示データ更新")

                    fields = [{
                        "name": "⚡ スリット気配",
                        "value": ", ".join(slit_msg_details),
                        "inline": False,
                    }]
                    send_discord_embed(
                        webhook_url=DISCORD_WEBHOOK_URL,
                        title=f"⚡ スリット気配検知！ 【{venue_japanese} {rno_str}R】",
                        description="展示・スリットデータで良好な気配を検知しました。",
                        fields=fields,
                        color=0x00E5FF,
                    )
                    notified_races.add(slit_race_id)
                    save_notified_races()

    existing_pending = {}
    if os.path.exists(PENDING_RESULTS_FILE):
        try:
            with open(PENDING_RESULTS_FILE, "r", encoding="utf-8") as f:
                existing_pending = json.load(f)
        except Exception:
            existing_pending = {}

    existing_pending.update(pending_results)

    try:
        with open(PENDING_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_pending, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ {PENDING_RESULTS_FILE} 保存エラー: {e}")

# ==========================================
# ⏱️ 実行エントリポイント
# ==========================================
if __name__ == "__main__":
    perform_login()
    load_checker_data()
    update_venues()

    for i in range(2):
        if today_venues:
            monitor_shinsum(list(today_venues))
        if i == 0:
            time.sleep(30)

    check_pickup_manshu_results()
