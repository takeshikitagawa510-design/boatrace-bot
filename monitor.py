import os
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# ==========================================
# 🎯 1. 初期設定
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

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
})

def send_discord_embed(title, description, fields=[], color=0x00FFFF):
    """リアルタイム通知用 Embed 送信関数"""
    if not DISCORD_WEBHOOK_URL: return
    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {"text": "競艇研究会 リアルタイムAIシグナル"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}")

def perform_login():
    print("🔑 ログイン中...")
    session.auth = (USER_ID, PASSWORD)
    try:
        session.post(LOGIN_URL, data={'id': USER_ID, 'pass': PASSWORD}, timeout=10)
        session.post(LOGIN_URL, data={'log': USER_ID, 'pwd': PASSWORD}, timeout=10)
    except Exception as e:
        print(f"⚠️ ログインエラー: {e}")

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
            if not href or any(skip in href for skip in ['login', 'logout', 'wp-']): continue

            if href.startswith('http') and 'boatrace-shinsum.com' in href: clean_url = href.split('?')[0]
            elif href.startswith('/'): clean_url = DATA_URL.rstrip('/') + href.split('?')[0]
            else: continue

            if clean_url != DATA_URL and clean_url != DATA_URL + '/' and clean_url not in today_venues:
                if any(x in clean_url for x in ['/boatrace/', '/checker/']): continue
                today_venues.add(clean_url)
    except Exception as e:
        print(f"⚠️ 会場更新エラー: {e}")

# ==========================================
# 📊 2. チェッカー確率解析
# ==========================================
def load_checker_data():
    global checker_data
    try:
        timestamp = int(time.time() * 1000)
        resp = session.get(f"{CHECKER_URL}?t={timestamp}", timeout=10)
        if resp.status_code == 401:
            perform_login()
            resp = session.get(f"{CHECKER_URL}?t={timestamp}", timeout=10)
            
        if resp.status_code == 200:
            checker_data = resp.json()
            print("✅ チェッカーデータ取得成功！")
        else:
            print(f"⚠️ チェッカー取得失敗: HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️ チェッカーエラー: {e}")

def get_real_probabilities(toban, waku, time_diff_val):
    if not checker_data or not toban or str(toban) not in checker_data: return None
    player_waku_data = next((w for w in checker_data[str(toban)] if w.get("n") == waku), None)
    if not player_waku_data: return None
    
    target_range = "大プラス" if time_diff_val >= 0.5 else "小プラス" if time_diff_val >= 0.0 else "小マイナス" if time_diff_val >= -0.5 else "大マイナス"
    for row in player_waku_data.get("rows", []):
        if row.get("name") == target_range:
            return {"r1": float(row.get("r1", 0.0)), "r2": float(row.get("r2", 0.0)), "r3": float(row.get("r3", 0.0))}
    return {"r1": float(player_waku_data.get("t1", 0.0)), "r2": float(player_waku_data.get("t2", 0.0)), "r3": float(player_waku_data.get("t3", 0.0))}

def generate_probability_eye(boats, target_waku=None):
    if not isinstance(boats, list) or len(boats) < 6: return "算出不可", "対象なし"
    analyzed_boats = []

    for i, b in enumerate(boats):
        waku = i + 1
        b_str = json.dumps(b, ensure_ascii=False)
        
        toban = None
        if isinstance(b, dict):
            toban = next((b[k] for k in ['id', 'no', 'toban', 'touban', 'racer_id'] if k in b and str(b[k]).isdigit() and 3000 <= int(b[k]) <= 6000), None)
        if not toban:
            found = re.findall(r'\b(3\d{3}|4\d{3}|5\d{3})\b', b_str)
            if found: toban = found[0]

        time_diff_val = 0.0
        for cand in ["+0.", "＋0.", "-0.", "－0.", "−0."]:
            if cand in b_str:
                try:
                    start_idx = b_str.find(cand)
                    sub_str = b_str[start_idx:start_idx+5].replace("＋", "+").replace("－", "-").replace("−", "-")
                    time_diff_val = float(''.join(c for c in sub_str if c in '+-.0123456789'))
                    break
                except: pass

        probs = get_real_probabilities(toban, waku, time_diff_val)
        if probs:
            analyzed_boats.append({"waku": waku, "r1": probs["r1"], "r2": probs["r2"], "r3": probs["r3"], "tdiff": time_diff_val})
        else:
            # データなし時もインコース偏重や出目順に逃げず、1着率・2着率・3着率のベース確率を設定
            base_r1 = 15.0 if waku == target_waku else (50.0 if waku == 1 else 10.0)
            base_r2 = 20.0 if waku != 1 else 15.0
            base_r3 = 20.0
            analyzed_boats.append({"waku": waku, "r1": base_r1, "r2": base_r2, "r3": base_r3, "tdiff": time_diff_val})

    # 1. 軸艇（1頭）の決定
    if target_waku and any(b["waku"] == target_waku for b in analyzed_boats):
        main_head = next(b for b in analyzed_boats if b["waku"] == target_waku)
    else:
        main_head = max(analyzed_boats[1:], key=lambda x: x["r1"])

    # 2. 相手艇（2着・3着）をシンサム理論（r2 / r3 確率の高い順）で選定
    others = [b for b in analyzed_boats if b["waku"] != main_head["waku"]]
    
    # 2着率（r2）が高い順に上位3艇を抽出して文字列化
    top_r2_boats = sorted(others, key=lambda x: x["r2"], reverse=True)[:3]
    r2_str = "".join(str(b["waku"]) for b in top_r2_boats)
    
    # 3着率（r3）が高い順に上位3艇を抽出して文字列化
    top_r3_boats = sorted(others, key=lambda x: x["r3"], reverse=True)[:3]
    r3_str = "".join(str(b["waku"]) for b in top_r3_boats)
    
    main_eye = f"{main_head['waku']}-{r2_str}-{r3_str}"

    # 外枠サブ目の計算（軸より外側の艇で1着率最大を軸にする）
    sub_pool = [b for b in analyzed_boats if b["waku"] > main_head["waku"]]
    sub_eye = "対象なし"
    if sub_pool:
        sub_head = max(sub_pool, key=lambda x: x["r1"])
        sub_others = [b for b in analyzed_boats if b["waku"] != sub_head["waku"]]
        sr2_str = "".join(str(b["waku"]) for b in sorted(sub_others, key=lambda x: x["r2"], reverse=True)[:3])
        sr3_str = "".join(str(b["waku"]) for b in sorted(sub_others, key=lambda x: x["r3"], reverse=True)[:3])
        sub_eye = f"{sub_head['waku']}-{sr2_str}-{sr3_str}"

    return main_eye, sub_eye

# ==========================================
# 🚀 3. 監視メイン
# ==========================================
def monitor_shinsum(venue_urls):
    global notified_races
    venue_name_map = {
        'kiryu': '桐生', 'toda': '戸田', 'edogawa': '江戸川', 'tokoname': '常滑',
        'mikuni': '三国', 'marugame': '丸亀', 'miyajima': '宮島', 'tokuyama': '徳山',
        'ashiya': '芦屋', 'omura': '大村', 'gamagori': '蒲郡', 'hamanako_sg': '浜名湖', 'hamanako': '浜名湖',
        'heiwajima': '平和島', 'tamagawa': '多摩川', 'tsu': '津', 'biwako': 'びわこ',
        'suminoe': '住之江', 'amagasaki': '尼崎', 'naruto': '鳴門', 'karatsu': '唐津',
        'kojima': '児島', 'wakamatsu': '若松', 'fukuoka': '福岡'
    }

    for venue_url in venue_urls:
        venue_id_name = venue_url.rstrip('/').split('/')[-1]
        is_joshi = '/joshi/' in venue_url
        venue_japanese = f"[女子]{venue_name_map.get(venue_id_name, venue_id_name)}" if is_joshi else venue_name_map.get(venue_id_name, venue_id_name)

        timestamp = int(time.time() * 1000)
        shinsum_data, arare_data = {}, {}
        
        try:
            s = session.get(f"{venue_url.rstrip('/')}/shinsum.json?t={timestamp}", timeout=8)
            if s.status_code == 200: shinsum_data = s.json()
        except: pass
        try:
            a = session.get(f"{venue_url.rstrip('/')}/arare.json?t={timestamp}", timeout=8)
            if a.status_code == 200: arare_data = a.json()
        except: pass

        all_race_keys = set(shinsum_data.keys()) | set(arare_data.keys())

        for rno_key in all_race_keys:
            try: rno_str = str(int(rno_key.replace('R', '')))
            except ValueError: continue

            slit_race_id = f"{venue_japanese}_{rno_str}_slit"
            rate_race_id = f"{venue_japanese}_{rno_str}_rate"
            kakusei_race_id = f"{venue_japanese}_{rno_str}_kakusei"

            boats = shinsum_data.get(rno_key, {}).get('boats', []) or arare_data.get(rno_key, {}).get('boats', [])
            if not boats: continue

            # ① 覚醒アラート
            if kakusei_race_id not in notified_races:
                kakusei_alerts = []
                if isinstance(boats, list):
                    for i, b in enumerate(boats):
                        b_str = json.dumps(b, ensure_ascii=False)
                        if ("シン Imperial" in b_str or "シン・" in b_str or "舟足覚醒型" in b_str) and ("+" in b_str or "＋" in b_str):
                            lbl = "🔥シン・覚醒" if "シン・" in b_str else "🌟舟足覚醒"
                            kakusei_alerts.append(f"{i+1}枠({lbl})")
                if kakusei_alerts:
                    main_eye, sub_eye = generate_probability_eye(boats)
                    fields = [
                        {"name": "🎯 メイン穴目", "value": f"`{main_eye}`", "inline": True},
                        {"name": "🔮 外枠サブ目", "value": f"`{sub_eye}`", "inline": True},
                        {"name": "⚡ 該当艇", "value": ", ".join(kakusei_alerts), "inline": False}
                    ]
                    send_discord_embed(
                        title=f"🚨 覚醒タイム発動！ 【{venue_japanese} {rno_str}R】",
                        description="対象艇の舟足・機力が大幅覚醒！高配当チャンスです。",
                        fields=fields,
                        color=0xFF0055
                    )
                    notified_races.add(kakusei_race_id)

            # ② 超抜・イン飛び
            if rate_race_id not in notified_races:
                w1_rate, other_rates = None, []
                for i, b in enumerate(boats):
                    s_1 = b.get('rate_1')
                    if s_1 is not None:
                        try:
                            clean = float(str(s_1).replace('%','').replace('+','').replace('＋','').replace('－','-').replace('−','-').strip())
                            if i == 0: w1_rate = clean
                            else: other_rates.append((clean, i+1))
                        except: continue
                if other_rates:
                    max_val, max_waku = max(other_rates, key=lambda x: x[0])
                    if max_val >= 10.0 or (w1_rate is not None and w1_rate < 0 and max_val >= 5.0):
                        is_chobatsu = max_val >= 10.0
                        title_str = "🌟 超抜チャンス到来！" if is_chobatsu else "🔥 イン飛び波乱警戒！"
                        
                        main_eye, sub_eye = generate_probability_eye(boats, target_waku=max_waku)
                        
                        fields = [
                            {"name": "📊 勝率データ", "value": f"1枠: `{w1_rate}%` ｜ 狙い `{max_waku}枠`: `+{max_val}%`", "inline": False},
                            {"name": "🎯 メイン穴目", "value": f"`{main_eye}`", "inline": True},
                            {"name": "🔮 外枠サブ目", "value": f"`{sub_eye}`", "inline": True}
                        ]
                        send_discord_embed(
                            title=f"{title_str} 【{venue_japanese} {rno_str}R】",
                            description="AI勝率偏向データを検知しました。",
                            fields=fields,
                            color=0xFFD700 if is_chobatsu else 0xFF4500
                        )
                        notified_races.add(rate_race_id)

            # ③ スリットアラート
            if slit_race_id not in notified_races:
                comb_text = json.dumps(shinsum_data.get(rno_key, {}), ensure_ascii=False) + json.dumps(arare_data.get(rno_key, {}), ensure_ascii=False)
                if "+" in comb_text or "＋" in comb_text:
                    details = []
                    if isinstance(boats, list):
                        for i, b in enumerate(boats):
                            b_str = json.dumps(b, ensure_ascii=False)
                            if "+" in b_str or "＋" in b_str:
                                val = next((cand.replace("＋","+") for cand in ["+0.1","+0.2","+0.3","＋0.1","＋0.2","＋0.3"] if cand in b_str), "確認")
                                details.append(f"{i+1}枠: {val}")
                    
                    fields = [{"name": "⚡ スリット気配", "value": ", ".join(details) if details else "展示データ更新", "inline": False}]
                    send_discord_embed(
                        title=f"⚡ スリットアラート発生！ 【{venue_japanese} {rno_str}R】",
                        description="展示・スリットデータでプラス気配を検知しました。",
                        fields=fields,
                        color=0x00E5FF
                    )
                    notified_races.add(slit_race_id)

if __name__ == "__main__":
    perform_login()
    load_checker_data()
    update_venues()

    start_time = time.time()
    while time.time() - start_time < 280:
        if today_venues:
            monitor_shinsum(list(today_venues))
        time.sleep(30)
