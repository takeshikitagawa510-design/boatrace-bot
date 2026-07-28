import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
import requests
from requests.auth import HTTPBasicAuth

# ==========================================
# 🎯 1. 初期設定 & 環境変数
# ==========================================
DATA_URL = "https://boatrace-shinsum.com/"
CHECKER_URL = "https://boatrace-shinsum.com/checker/shinsum_checker.json"

USER_ID = os.environ.get("SHINSUM_USER", "sum")
PASSWORD = os.environ.get("SHINSUM_PASS", "art")

# Webhook URLs
DISCORD_WEBHOOK_URL = os.environ.get("MONITOR_DISCORD_WEBHOOK_URL")  # ⚡ リアルタイムAIアラート用
RESULT_WEBHOOK_URL = os.environ.get("RESULT_DISCORD_WEBHOOK_URL")   # 🎯 的中・万舟実績用

# ------------------------------------------
# 💾 通知済みデータの永続化
# ------------------------------------------
CACHE_FILE = "notified_races.json"
PENDING_PICKUPS_FILE = "pending_pickup_races.json"  # 朝一ピックアップ万舟追跡用

notified_races = set()
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            notified_races = set(json.load(f))
        print(f"📦 過去の通知済みデータ ({len(notified_races)}件) を読み込みました。")
    except Exception as e:
        print(f"⚠️ キャッシュ読み込みエラー: {e}")


def save_notified_races():
    """通知済みデータをJSONファイルに保存"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(notified_races), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ キャッシュ保存エラー: {e}")


today_venues = set()
checker_data = {}

JST = timezone(timedelta(hours=+9), "JST")

# Basic認証オブジェクト
AUTH = HTTPBasicAuth(USER_ID, PASSWORD)

session = requests.Session()
session.auth = AUTH
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
})


def send_discord_embed(webhook_url, title, description, fields=[], color=0x00FFFF):
    """DiscordへリッチなEmbed（カード型）メッセージを送信"""
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
        print(f"📡 Discord送信結果: HTTP {res.status_code}")
    except Exception as e:
        print(f"⚠️ Discord通信エラー: {e}")


def perform_login():
    """疎通・認証確認"""
    try:
        resp = session.get(DATA_URL, auth=AUTH, timeout=10)
        if resp.status_code == 200:
            print("🔑 Basic認証成功 (Status Code: 200)")
        else:
            print(f"⚠️ 認証応答コード: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ 通信エラー: {e}")


def update_venues():
    """全会場のURLを取得"""
    global today_venues
    try:
        resp = session.get(DATA_URL, auth=AUTH, timeout=10)
        if resp.status_code == 401:
            perform_login()
            resp = session.get(DATA_URL, auth=AUTH, timeout=10)

        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a"):
            href = a.get("href")
            if not href or any(
                skip in href for skip in ["login", "logout", "wp-", "/checker/"]
            ):
                continue

            if href.startswith("http") and "boatrace-shinsum.com" in href:
                full_url = href
            elif href.startswith("/"):
                full_url = DATA_URL.rstrip("/") + href
            else:
                continue

            if full_url not in [
                DATA_URL,
                DATA_URL + "/",
                DATA_URL + "login",
            ]:
                today_venues.add(full_url)

        print(f"✅ 巡回対象の会場URL ({len(today_venues)}件): {list(today_venues)}")

    except Exception as e:
        print(f"⚠️ 会場更新エラー: {e}")


# ==========================================
# 📊 2. AI確率解析ロジック
# ==========================================
def load_checker_data():
    global checker_data
    try:
        timestamp = int(time.time() * 1000)
        resp = session.get(
            f"{CHECKER_URL}?t={timestamp}", auth=AUTH, timeout=10
        )
        if resp.status_code == 401:
            perform_login()
            resp = session.get(
                f"{CHECKER_URL}?t={timestamp}", auth=AUTH, timeout=10
            )

        if resp.status_code == 200:
            checker_data = resp.json()
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
        "大プラス"
        if time_diff_val >= 0.5
        else (
            "小プラス"
            if time_diff_val >= 0.0
            else "小マイナス" if time_diff_val >= -0.5 else "大マイナス"
        )
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
        for exact_key in [
            "id", "no", "toban", "register_id", "player_id", "touban"
        ]:
            if (
                exact_key in b
                and str(b[exact_key]).isdigit()
                and 3000 <= int(b[exact_key]) <= 6000
            ):
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
                    time_diff_val = float(
                        "".join(c for c in sub_str if c in "+-.0123456789")
                    )
                    break
                except:
                    pass

        is_alert_target = ("Imperial" in b_str or "覚醒" in b_str) and (
            "+" in b_str or "＋" in b_str
        )

        probs = get_real_probabilities(toban, waku, time_diff_val)
        if probs:
            has_valid_checker = True
            analyzed_boats.append({
                "waku": waku,
                "r1": probs["r1"],
                "r2": probs["r2"],
                "r3": probs["r3"],
                "is_alert": is_alert_target,
                "tdiff": time_diff_val,
            })
        else:
            analyzed_boats.append({
                "waku": waku,
                "r1": 0.0,
                "r2": 0.0,
                "r3": 0.0,
                "is_alert": is_alert_target,
                "tdiff": time_diff_val,
            })

    if has_valid_checker:
        pool_2to6 = analyzed_boats[1:]
        main_head = max(pool_2to6, key=lambda x: x["r1"])

        other_boats = [
            b for b in analyzed_boats if b["waku"] != main_head["waku"]
        ]
        top_r2_boats = sorted(
            other_boats, key=lambda x: x["r2"], reverse=True
        )[:3]
        top_r3_boats = sorted(
            other_boats, key=lambda x: x["r3"], reverse=True
        )[:3]

        r2_str = "".join(str(b["waku"]) for b in top_r2_boats)
        r3_str = "".join(str(b["waku"]) for b in top_r3_boats)
        main_eye = f"{main_head['waku']}-{r2_str}-{r3_str}"

        sub_pool = [
            b for b in analyzed_boats if b["waku"] > main_head["waku"]
        ]
        sub_eye = "対象なし"
        if sub_pool:
            sub_head = max(sub_pool, key=lambda x: x["r1"])
            sub_others = [
                b for b in analyzed_boats if b["waku"] != sub_head["waku"]
            ]
            sub_r2_boats = sorted(
                sub_others, key=lambda x: x["r2"], reverse=True
            )[:3]
            sub_r3_boats = sorted(
                sub_others, key=lambda x: x["r3"], reverse=True
            )[:3]
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
            key=lambda x: x["tdiff"],
            reverse=True,
        )
        r2_str = "".join(str(b["waku"]) for b in other_boats[:3])
        r3_str = "".join(str(b["waku"]) for b in other_boats[:4])
        main_eye = f"{main_head['waku']}-{r2_str}-{r3_str}"

        sub_pool = [
            b for b in analyzed_boats if b["waku"] > main_head["waku"]
        ]
        sub_eye = "対象なし"
        if sub_pool:
            sub_head = max(sub_pool, key=lambda x: x["tdiff"])
            sub_others = sorted(
                [b for b in analyzed_boats if b["waku"] != sub_head["waku"]],
                key=lambda x: x["tdiff"],
                reverse=True,
            )
            sub_r2_str = "".join(str(b["waku"]) for b in sub_others[:3])
            sub_r3_str = "".join(str(b["waku"]) for b in sub_others[:4])
            sub_eye = f"{sub_head['waku']}-{sub_r2_str}-{sub_r3_str}"

        return main_eye, sub_eye


# ==========================================
# 🚀 3. リアルタイムAI監視ロジック
# ==========================================
def monitor_shinsum(venue_urls):
    global notified_races
    venue_name_map = {
        "kiryu": "桐生", "toda": "戸田", "edogawa": "江戸川", "tokoname": "常滑",
        "mikuni": "三国", "marugame": "丸亀", "miyajima": "宮島", "tokuyama": "徳山",
        "ashiya": "芦屋", "omura": "大村", "gamagori": "蒲郡", "hamanako_sg": "浜名湖",
        "hamanako": "浜名湖", "heiwajima": "平和島", "tamagawa": "多摩川", "tsu": "津",
        "biwako": "びわこ", "suminoe": "住之江", "amagasaki": "尼崎", "naruto": "鳴門",
        "karatsu": "唐津", "kojima": "児島", "wakamatsu": "若松", "fukuoka": "福岡",
        "shimonoseki": "下関",
    }

    for venue_url in venue_urls:
        parsed = urlparse(venue_url)
        clean_base_url = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")
        )

        venue_id_name = parsed.path.rstrip("/").split("/")[-1]
        is_joshi = "/joshi/" in parsed.path
        venue_japanese = (
            f"[女子]{venue_name_map.get(venue_id_name, venue_id_name)}"
            if is_joshi
            else venue_name_map.get(venue_id_name, venue_id_name)
        )

        timestamp = int(time.time() * 1000)
        shinsum_data, arare_data = {}, {}

        try:
            s_resp = session.get(
                f"{clean_base_url}/shinsum.json?t={timestamp}",
                auth=AUTH,
                timeout=8,
            )
            if s_resp.status_code == 200:
                shinsum_data = s_resp.json()
            elif s_resp.status_code == 401:
                perform_login()
        except Exception as e:
            print(f"⚠️ {venue_japanese} shinsum.json 取得エラー: {e}")

        try:
            a_resp = session.get(
                f"{clean_base_url}/arare.json?t={timestamp}",
                auth=AUTH,
                timeout=8,
            )
            if a_resp.status_code == 200:
                arare_data = a_resp.json()
        except Exception as e:
            print(f"⚠️ {venue_japanese} arare.json 取得エラー: {e}")

        all_race_keys = set(shinsum_data.keys()) | set(arare_data.keys())

        for rno_key in all_race_keys:
            try:
                rno_str = str(int(rno_key.replace("R", "")))
            except ValueError:
                continue

            slit_race_id = f"{venue_japanese}_{rno_str}_slit"
            rate_race_id = f"{venue_japanese}_{rno_str}_rate"
            kakusei_race_id = f"{venue_japanese}_{rno_str}_kakusei"

            boats = (
                shinsum_data.get(rno_key, {}).get("boats", [])
                or arare_data.get(rno_key, {}).get("boats", [])
            )
            if not boats:
                continue

            # ① 覚醒タイム ✕ 推奨買い目
            if kakusei_race_id not in notified_races:
                kakusei_alerts = []
                is_triggered = False
                if isinstance(boats, list):
                    for i, b in enumerate(boats):
                        teiban = i + 1
                        b_str = json.dumps(b, ensure_ascii=False)
                        if ("Imperial" in b_str or "覚醒" in b_str) and (
                            "+" in b_str or "＋" in b_str
                        ):
                            is_triggered = True
                            type_label = (
                                "🔥MAX覚醒"
                                if "Imperial" in b_str
                                else "🌟機力覚醒"
                            )
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

            # ② 勝率判定（イン飛び・超抜チャンス）✕ 推奨買い目
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
                                .replace("%", "")
                                .replace("+", "")
                                .replace("＋", "")
                                .replace("－", "-")
                                .replace("−", "-")
                                .strip()
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
                    other_max_val, other_max_waku = max(
                        other_rates, key=lambda x: x[0]
                    )
                    is_chobatsu = other_max_val >= 10.0
                    is_in_tobi = (
                        w1_rate is not None
                        and w1_rate < 0
                        and other_max_val >= 5.0
                    )

                    if is_chobatsu or is_in_tobi:
                        title = (
                            "🌟 超抜シグナル到来！"
                            if is_chobatsu
                            else "🔥 イン波乱警戒シグナル！"
                        )
                        w1_str = (
                            f"+{w1_rate}"
                            if (w1_rate is not None and w1_rate > 0)
                            else f"{w1_rate}" if w1_rate is not None else "不明"
                        )
                        other_str = (
                            f"+{other_max_val}"
                            if other_max_val > 0
                            else f"{other_max_val}"
                        )

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

            # ③ スリットアラート
            if slit_race_id not in notified_races:
                race_shinsum_str = json.dumps(
                    shinsum_data.get(rno_key, {}), ensure_ascii=False
                )
                race_arare_str = json.dumps(
                    arare_data.get(rno_key, {}), ensure_ascii=False
                )
                combined_race_text = race_shinsum_str + race_arare_str
                if "+" in combined_race_text or "＋" in combined_race_text:
                    slit_msg_details = []
                    if isinstance(boats, list):
                        for i, b in enumerate(boats):
                            teiban = i + 1
                            b_str = json.dumps(b, ensure_ascii=False)
                            if "+" in b_str or "＋" in b_str:
                                val = "確認"
                                for cand in [
                                    "+0.1", "+0.2", "+0.3",
                                    "＋0.1", "＋0.2", "＋0.3",
                                ]:
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


# ==========================================
# 💰 4. 朝一万舟ヒット（10,000円以上）自動チェック
# ==========================================
def check_pickup_results():
    if not os.path.exists(PENDING_PICKUPS_FILE):
        return

    try:
        with open(PENDING_PICKUPS_FILE, "r", encoding="utf-8") as f:
            pending_pickups = json.load(f)
    except Exception:
        pending_pickups = {}

    if not pending_pickups:
        return

    print(f"🔍 朝一万舟監視対象: {len(pending_pickups)}件")
    venue_en_map = {
        "桐生": "kiryu", "戸田": "toda", "江戸川": "edogawa", "常滑": "tokoname",
        "三国": "mikuni", "丸亀": "marugame", "宮島": "miyajima", "徳山": "tokuyama",
        "芦屋": "ashiya", "大村": "omura", "蒲郡": "gamagori", "浜名湖": "hamanako",
        "平和島": "heiwajima", "多摩川": "tamagawa", "津": "tsu", "びわこ": "biwako",
        "住之江": "suminoe", "尼崎": "amagasaki", "鳴門": "naruto", "唐津": "karatsu",
        "児島": "kojima", "若松": "wakamatsu", "福岡": "fukuoka", "下関": "shimonoseki",
    }

    updated_pickups = pending_pickups.copy()
    for race_key, info in list(pending_pickups.items()):
        v_name = str(info.get("v", "")).strip()
        rno = info.get("r")
        date_str = str(info.get("date", ""))

        venue_en = venue_en_map.get(v_name, v_name)
        res_url = f"{DATA_URL.rstrip('/')}/data/{venue_en}/{date_str}/r{rno}/result.json"

        try:
            r = session.get(res_url, timeout=5)
            if r.status_code != 200:
                continue

            result_data = r.json()
            sanrentan = result_data.get("sanrentan", {})
            winning_combo = sanrentan.get("combo")
            payout = sanrentan.get("payout", 0)

            if winning_combo:
                if payout >= 10000:
                    send_discord_embed(
                        webhook_url=RESULT_WEBHOOK_URL,
                        title=f"💣【朝一ピックアップ万舟ヒット！】 {v_name} {rno}R",
                        description="朝一AI解析でピックアップした波乱期待値レースにて**万舟が発生**しました！",
                        fields=[
                            {"name": "📍 対象レース", "value": f"{v_name} {rno}R", "inline": True},
                            {"name": "💰 確定配当", "value": f"**3連単 {winning_combo} / {payout:,}円**", "inline": True},
                            {"name": "🔥 期待値スコア", "value": f"{info.get('s', 0)}点", "inline": True},
                        ],
                        color=0xFF0055,
                    )
                del updated_pickups[race_key]
        except Exception as e:
            print(f"⚠️ 万舟結果確認エラー ({race_key}): {e}")

    with open(PENDING_PICKUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_pickups, f, ensure_ascii=False, indent=2)


# ==========================================
# ⏱️ 5. 実行エントリポイント
# ==========================================
if __name__ == "__main__":
    perform_login()
    load_checker_data()
    update_venues()

    start_time = time.time()
    # 5分間（240秒）のループ実行
    while time.time() - start_time < 240:
        if today_venues:
            monitor_shinsum(list(today_venues))
        # 朝一ピックアップ万舟の自動判定・実績投稿
        check_pickup_results()
        time.sleep(30)
