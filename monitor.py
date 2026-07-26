import os
import time
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# ==========================================
# 🎯 1. 初期設定 (環境変数から安全に取得)
# ==========================================
LOGIN_URL = "https://boatrace-shinsum.com/login"
DATA_URL = "https://boatrace-shinsum.com/"
CHECKER_URL = "https://boatrace-shinsum.com/checker/shinsum_checker.json"

USER_ID = os.environ.get('SHINSUM_USER', 'sum')
PASSWORD = os.environ.get('SHINSUM_PASS', 'art')
DISCORD_WEBHOOK_URL = os.environ.get('MONITOR_DISCORD_WEBHOOK_URL')

notified_races = set()
today_venues = set()
checker_data = {}

JST = timezone(timedelta(hours=+9), 'JST')
last_date = datetime.now(JST).strftime('%Y%m%d')

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
})

def send_discord_notify(message):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ MONITOR_DISCORD_WEBHOOK_URL が設定されていないため送信をスキップします。")
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}")

def perform_login():
    print("🔑 サイトにログインしています...")
    session.auth = (USER_ID, PASSWORD)
    try:
        session.post(LOGIN_URL, data={'id': USER_ID, 'pass': PASSWORD}, timeout=10)
        session.post(LOGIN_URL, data={'log': USER_ID, 'pwd': PASSWORD}, timeout=10)
    except Exception as e:
        print(f"⚠️ ログイン通信エラー: {e}")

def update_venues():
    global today_venues
    try:
        resp = session.get(DATA_URL, timeout=10)
        if resp.status_code == 401:
            perform_login()
            resp = session.get(DATA_URL, timeout=10)

        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')

        for a in soup.find_all('a'):
            href = a.get('href')
            if not href or any(skip in href for skip in ['login', 'logout', 'wp-']):
                continue

            if href.startswith('http') and 'boatrace-shinsum.com' in href:
                clean_url = href.split('?')[0]
            elif href.startswith('/'):
                clean_url = DATA_URL.rstrip('/') + href.split('?')[0]
            else:
                continue

            if clean_url != DATA_URL and clean_url != DATA_URL + '/' and clean_url not in today_venues:
                if any(x in clean_url for x in ['/boatrace/', '/joshi/', '/checker/']):
                    continue
                today_venues.add(clean_url)
                print(f"🆕 新しい会場を追加しました: {clean_url}")
    except Exception as e:
        print(f"⚠️ 会場リスト更新エラー: {e}")

# ==========================================
# 📊 2. チェッカー確率解析ロジック
# ==========================================
def load_checker_data():
    global checker_data
    print("📡 チェッカーの最新マスターデータをロード中...")
    try:
        timestamp = int(time.time() * 1000)
        resp = session.get(f"{CHECKER_URL}?t={timestamp}", timeout=10)
        if resp.status_code == 200:
            checker_data = resp.json()
            print(f"✅ チェッカーデータロード完了 ({len(checker_data)}選手分)")
        else:
            print(f"⚠️ チェッカー取得失敗: HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️ チェッカーデータロードエラー: {e}")

def get_real_probabilities(toban, waku, time_diff_val):
    if not checker_data or not toban or str(toban) not in checker_data:
        return None
    player_waku_data = None
    for w_data in checker_data[str(toban)]:
        if w_data.get("n") == waku:
            player_waku_data = w_data
            break
    if not player_waku_data:
        return None
    if time_diff_val >= 0.5: target_range = "大プラス"
    elif 0.0 <= time_diff_val < 0.5: target_range = "小プラス"
    elif -0.5 <= time_diff_val < 0.0: target_range = "小マイナス"
    else: target_range = "大マイナス"
    for row in player_waku_data.get("rows", []):
        if row.get("name") == target_range:
            return {"r1": float(row.get("r1", 0.0)), "r2": float(row.get("r2", 0.0)), "r3": float(row.get("r3", 0.0))}
    return {"r1": float(player_waku_data.get("t1", 0.0)), "r2": float(player_waku_data.get("t2", 0.0)), "r3": float(player_waku_data.get("t3", 0.0))}

def generate_probability_eye(boats):
    if not isinstance(boats, list) or len(boats) < 6:
        return "データ不足により算出不可", "対象なし"

    analyzed_boats = []
    has_valid_checker = False

    for i, b in enumerate(boats):
        waku = i + 1
        b_str = json.dumps(b, ensure_ascii=False)

        toban = None
        for exact_key in ['id', 'no', 'toban', 'register_id', 'player_id', 'touban']:
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
                    sub_str = b_str[start_idx:start_idx+5].replace("＋", "+").replace("－", "-").replace("−", "-")
                    time_diff_val = float(''.join(c for c in sub_str if c in '+-.0123456789'))
                    break
                except: pass

        is_alert_target = ("シン Imperial" in b_str or "シン・" in b_str or "舟足覚醒型" in b_str) and ("+" in b_str or "＋" in b_str)

        probs = get_real_probabilities(toban, waku, time_diff_val)
        if probs:
            has_valid_checker = True
            analyzed_boats.append({"waku": waku, "r1": probs["r1"], "r2": probs["r2"], "r3": probs["r3"], "is_alert": is_alert_target, "tdiff": time_diff_val})
        else:
            analyzed_boats.append({"waku": waku, "r1": 0.0, "r2": 0.0, "r3": 0.0, "is_alert": is_alert_target, "tdiff": time_diff_val})

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
        other_boats = sorted([b for b in analyzed_boats if b["waku"] != main_head["waku"]], key=lambda x: x["tdiff"], reverse=True)
        
        r2_str = "".join(str(b["waku"]) for b in other_boats[:3])
        r3_str = "".join(str(b["waku"]) for b in other_boats[:4])
        
        main_eye = f"{main_head['waku']}-{r2_str}-{r3_str}"

        sub_pool = [b for b in analyzed_boats if b["waku"] > main_head["waku"]]
        sub_eye = "対象なし"
        if sub_pool:
            sub_head = max(sub_pool, key=lambda x: x["tdiff"])
            sub_others = sorted([b for b in analyzed_boats if b["waku"] != sub_head["waku"]], key=lambda x: x["tdiff"], reverse=True)
            
            sub_r2_str = "".join(str(b["waku"]) for b in sub_others[:3])
            sub_r3_str = "".join(str(b["waku"]) for b in sub_others[:4])
            
            sub_eye = f"{sub_head['waku']}-{sub_r2_str}-{sub_r3_str}"
            
        return main_eye, sub_eye

# ==========================================
# 🚀 3. 監視メインロジック
# ==========================================
def monitor_shinsum(venue_urls):
    global notified_races
    now = datetime.now(JST)

    print(f"[{now.strftime('%H:%M:%S')}] ⏳ {len(venue_urls)}会場を巡回中...")

    venue_name_map = {
        'kiryu': '桐生', 'toda': '戸田', 'edogawa': '江戸川', 'tokoname': '常滑',
        'mikuni': '三国', 'marugame': '丸亀', 'miyajima': '宮島', 'tokuyama': '徳山',
        'ashiya': '芦屋', 'omura': '大村', 'gamagori': '蒲郡', 'hamanako_sg': '浜名湖',
        'heiwajima': '平和島', 'tamagawa': '多摩川', 'tsu': '津', 'biwako': 'びわこ',
        'kojima': '児島', 'wakamatsu': '若松', 'fukuoka': '福岡'
    }

    for venue_url in venue_urls:
        venue_id_name = venue_url.rstrip('/').split('/')[-1]
        venue_japanese = venue_name_map.get(venue_id_name, venue_id_name)
        timestamp = int(time.time() * 1000)

        shinsum_data, arare_data = {}, {}
        
        try:
            s_resp = session.get(f"{venue_url.rstrip('/')}/shinsum.json?t={timestamp}", timeout=8)
            if s_resp.status_code == 200: 
                shinsum_data = s_resp.json()
            elif s_resp.status_code == 401:
                print(f"🔐 認証切れを検知。再ログインします...")
                perform_login()
        except Exception:
            pass

        try:
            a_resp = session.get(f"{venue_url.rstrip('/')}/arare.json?t={timestamp}", timeout=8)
            if a_resp.status_code == 200: 
                arare_data = a_resp.json()
        except Exception:
            pass

        all_race_keys = set(shinsum_data.keys()) | set(arare_data.keys())

        for rno_key in all_race_keys:
            try: rno_str = str(int(rno_key.replace('R', '')))
            except ValueError: continue

            slit_race_id = f"{venue_japanese}_{rno_str}_slit"
            rate_race_id = f"{venue_japanese}_{rno_str}_rate"
            kakusei_race_id = f"{venue_japanese}_{rno_str}_kakusei"

            boats = shinsum_data.get(rno_key, {}).get('boats', []) or arare_data.get(rno_key, {}).get('boats', [])
            if not boats: continue

            # ① 覚醒タイム
            if kakusei_race_id not in notified_races:
                kakusei_alerts = []
                is_triggered = False
                if isinstance(boats, list):
                    for i, b in enumerate(boats):
                        teiban = i + 1
                        b_str = json.dumps(b, ensure_ascii=False)
                        if ("シン Imperial" in b_str or "シン・" in b_str or "舟足覚醒型" in b_str) and ("+" in b_str or "＋" in b_str):
                            is_triggered = True
                            type_label = "🔥【シン・覚醒】" if "シン・" in b_str else "🌟【舟足覚醒】"
                            kakusei_alerts.append(f"{teiban}枠({type_label})")
                if is_triggered:
                    main_eye, sub_eye = generate_probability_eye(boats)
                    msg = f"🚨【覚醒タイム発動チャンス！】\n会場: {venue_japanese} {rno_str}R\n該当: {', '.join(kakusei_alerts)}\n-------------------------\n📊 確率データ算出・推奨買い目\n🎯 メイン穴目: {main_eye}\n🔮 外枠サブ目: {sub_eye}"
                    send_discord_notify(msg)
                    print(f"🚨 買い目付き覚醒通知送信: {kakusei_race_id}")
                    notified_races.add(kakusei_race_id)

            # ② 勝率判定
            if rate_race_id not in notified_races:
                w1_rate = None
                other_rates = []
                for i, b in enumerate(boats):
                    teiban = i + 1
                    shin_1chaku = b.get('rate_1')
                    if shin_1chaku is not None:
                        try:
                            clean_str = str(shin_1chaku).replace('%', '').replace('+', '').replace('＋', '').replace('－', '-').replace('−', '-').strip()
                            if clean_str:
                                diff = float(clean_str)
                                if teiban == 1: w1_rate = diff
                                elif 2 <= teiban <= 6: other_rates.append((diff, teiban))
                        except: continue
                if other_rates:
                    other_max_val, other_max_waku = max(other_rates, key=lambda x: x[0])
                    is_chobatsu = other_max_val >= 10.0
                    is_in_tobi = (w1_rate is not None and w1_rate < 0 and other_max_val >= 5.0)

                    if is_chobatsu or is_in_tobi:
                        title = "🌟【超抜チャンス！】" if is_chobatsu else "🔥【イン飛びチャンス！】"
                        w1_str = f"+{w1_rate}" if (w1_rate is not None and w1_rate > 0) else f"{w1_rate}" if w1_rate is not None else "不明"
                        other_str = f"+{other_max_val}" if other_max_val > 0 else f"{other_max_val}"

                        main_eye, sub_eye = generate_probability_eye(boats)

                        msg = (
                            f"{title}\n会場: {venue_japanese} {rno_str}R\n"
                            f"1枠: {w1_str}% ｜ 狙い目 {other_max_waku}枠: {other_str}%\n"
                            f"-------------------------\n"
                            f"📊 確率データ算出・推奨買い目\n"
                            f"🎯 メイン穴目: {main_eye}\n"
                            f"🔮 外枠サブ目: {sub_eye}"
                        )
                        send_discord_notify(msg)
                        print(f"🎯 買い目付き激アツ通知送信: {rate_race_id}")
                        notified_races.add(rate_race_id)

            # ③ スリットアラート
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
                                    if cand in b_str: val = cand.replace("＋", "+"); break
                                slit_msg_details.append(f"{teiban}枠: {val}")
                    if not slit_msg_details: slit_msg_details.append("展示データ更新")
                    slit_msg = f"⚡【スリットアラート発生！】\n会場: {venue_japanese} {rno_str}R\n状況: " + ", ".join(slit_msg_details)
                    send_discord_notify(slit_msg)
                    print(f"⚡ スリット検知通知送信: {slit_race_id}")
                    notified_races.add(slit_race_id)

# ==========================================
# ⏱️ 4. 実行単体処理 (1回のジョブで約5分巡回)
# ==========================================
if __name__ == "__main__":
    print("🚀 舟券太郎 確率選定・自動買い目出力AIモニター 起動！")
    perform_login()
    load_checker_data()
    update_venues()

    # 1回の起動で数回（約5分間）ループして即終了させる構成（GitHub Actions用）
    start_time = time.time()
    # 約5分間巡回して終了する
    while time.time() - start_time < 280:
        if today_venues:
            monitor_shinsum(list(today_venues))
        time.sleep(30) # 30秒ごとにチェック
