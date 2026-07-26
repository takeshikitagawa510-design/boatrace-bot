import os
import json
import re
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

# ==========================================
# 🎯 基本設定 (GitHub Secrets から URL を取得)
# ==========================================
CHANCE_DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

JST = timezone(timedelta(hours=+9), 'JST')
TARGET_DATE = datetime.now(JST).strftime('%Y%m%d')
DISPLAY_DATE = datetime.now(JST).strftime('%Y/%m/%d')
JSON_FILENAME = 'scoring_dictionary.json'
EXCLUDE_VENUES = ['03', '04', '09']

VENUE_NAMES = {
    '01':'桐生','02':'戸田','05':'多摩川','06':'浜名湖','07':'蒲郡','08':'常滑',
    '10':'三国','11':'びわこ','12':'住之江','13':'尼崎','14':'鳴門','15':'丸亀',
    '16':'児島','17':'宮島','18':'徳山','19':'下関','20':'若松','21':'芦屋',
    '22':'福岡','23':'唐津','24':'大村'
}

try:
    with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
        scoring_dict = json.load(f)
except Exception:
    scoring_dict = {'manshu_overall':{}, 'in_tobi_overall':{}}

def send_discord_notify(message):
    """Discordへメッセージを送信する（長文自動分割対応）"""
    if not CHANCE_DISCORD_WEBHOOK_URL:
        print("⚠️ DISCORD_WEBHOOK_URL が設定されていないため送信をスキップします。")
        return
    
    # 2000文字制限対策：1900文字単位で分割送信
    max_len = 1900
    lines = message.split('\n')
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_len:
            try:
                requests.post(CHANCE_DISCORD_WEBHOOK_URL, json={"content": current_chunk}, timeout=10)
            except Exception as e:
                print(f"⚠️ Discord通信エラー: {e}")
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk:
        try:
            res = requests.post(CHANCE_DISCORD_WEBHOOK_URL, json={"content": current_chunk}, timeout=10)
            if res.status_code in [200, 204]:
                print("✅ Discord送信成功！")
            else:
                print(f"⚠️ Discord送信エラー: HTTP {res.status_code}")
        except Exception as e:
            print(f"⚠️ Discord通信エラー: {e}")

# ==========================================
# 🚀 【万舟専用】 スキャン開始
# ==========================================
def main():
    manshu_races = []

    print(f"⚔️ 【万舟スキャナー】 {TARGET_DATE} 実行中...\n")

    for jcd in range(1, 25):
        jcd_str = f"{jcd:02d}"
        if jcd_str in EXCLUDE_VENUES or jcd_str not in VENUE_NAMES:
            continue

        check_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={jcd_str}&hd={TARGET_DATE}"
        try:
            res = cffi_requests.get(check_url, impersonate="chrome110", timeout=5)
            if "データがありません" in res.text: continue
        except: continue

        print(f"🏟️ 【{VENUE_NAMES[jcd_str]}】 解析中...")

        for rno in range(1, 13):
            try:
                list_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd_str}&hd={TARGET_DATE}"
                response = cffi_requests.get(list_url, impersonate="chrome110", timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                tbodys = soup.find_all('tbody', class_='is-fs12')
                if len(tbodys) < 6: continue

                racers = {}
                for w, tbody in enumerate(tbodys[:6], 1):
                    name_a = tbody.find('div', class_='is-fs18 is-fBold').find('a')
                    raw_name = name_a.get_text(strip=True)
                    name = re.sub(r'\s+', '', raw_name)

                    txt = tbody.get_text(separator=' ')
                    # 勝率抽出
                    win_rates = re.findall(r'(?<!\d)([1-9]\.\d{2})(?!\d)', txt)
                    national_rate = float(win_rates[0]) if len(win_rates) > 0 else 0.0
                    local_rate = float(win_rates[1]) if len(win_rates) > 1 else 0.0

                    # ST抽出
                    st_m = re.findall(r'(?:^|\s|[FL])\.([0-9]{2})\b', txt)
                    t_sts = [float(x)/100 for x in st_m if x.isdigit()]
                    sec_st = sum(t_sts)/len(t_sts) if t_sts else 9.99

                    racers[w] = {
                        'name': name, 'national': national_rate, 'local': local_rate,
                        'sec_st': sec_st, 'has_sec': len(t_sts) > 0
                    }

                # 🚨 共通スキップ条件：初日（ST未算出が1人でもいるレース）はパス
                if any(not racers[w]['has_sec'] for w in range(1, 7)):
                    continue

                r1 = racers[1]

                # ==========================================
                # ⚔️ 万舟チェッカー（刺客・隣叩き）
                # ==========================================
                is_valid_manshu = False
                found_assassin_logs = []

                for w in range(2, 7):
                    r = racers[w]
                    m_pt = scoring_dict.get('manshu_overall', {}).get(r['name'], 0)
                    if m_pt > 0 and r['sec_st'] <= 0.15:
                        inner_st = racers[w-1]['sec_st']
                        if inner_st != 9.99 and (inner_st - r['sec_st']) >= 0.03:
                            is_valid_manshu = True
                            gap = round(inner_st - r['sec_st'], 2)
                            found_assassin_logs.append(f"🎯 {w}号艇({r['name']}): 万舟実績(+{m_pt}pt) ＆ 隣を[{gap}]差で叩く")

                if is_valid_manshu:
                    it = scoring_dict.get('in_tobi_overall', {}).get(r1['name'], 0)
                    if it > 0:
                        other_makers = []
                        m_total = 0
                        for wk in range(2, 7):
                            pt = scoring_dict.get('manshu_overall', {}).get(racers[wk]['name'], 0)
                            if pt > 0:
                                m_total += pt
                                if not any(f"{wk}号艇" in log for log in found_assassin_logs):
                                    other_makers.append(f"   (予) {wk}号艇({racers[wk]['name']}): 万舟実績(+{pt}pt)")

                        final_score = it + m_total + 30
                        if final_score >= 150:
                            c_logs = [f"💣 1号艇({r1['name']}): イン飛実績 (+{it}pt)"] + found_assassin_logs + other_makers
                            manshu_races.append({'v': VENUE_NAMES[jcd_str], 'r': rno, 's': final_score, 'd': c_logs})

            except Exception:
                continue

    # ==========================================
    # 📊 結果表示（画面出力）
    # ==========================================
    print("\n" + "★"*80)
    print("⚔️ 【万舟チェッカー】 回収率爆発・波乱狙い (上位表示)")
    print("★"*80)
    if not manshu_races:
        print("条件をクリアした『真の刺客レース』はありませんでした。")
    else:
        manshu_races.sort(key=lambda x: x['s'], reverse=True)
        for r in manshu_races[:25]:
            print(f"🔥 【{r['v']} {r['r']}R】 スコア: {r['s']}点")
            for d in r['d']: print("   " + d)
            print("-" * 80)

    # ==========================================
    # 📡 Discord送信処理（画面出力と同じ上位25件を全件送信）
    # ==========================================
    discord_msg = f"📢 **【本日の万舟チャンスレース】 ({DISPLAY_DATE})**\n\n"

    discord_msg += "⚔️ **【万舟・波乱狙い】**\n"
    if not manshu_races:
        discord_msg += "・本日は該当レースなし\n"
    else:
        for r in manshu_races[:25]:
            assassin_targets = []
            for line in r['d']:
                if '🎯' in line:
                    target_part = line.split('🎯')[1].split(':')[0].strip()
                    assassin_targets.append(target_part)
            
            target_str = " / ".join(assassin_targets) if assassin_targets else "刺客あり"
            discord_msg += f"🔥 **{r['v']} {r['r']}R** ｜ 狙い: {target_str}\n"

    print("\n📡 指定のDiscordチャンネルへ送信中...")
    send_discord_notify(discord_msg)

if __name__ == '__main__':
    main()
