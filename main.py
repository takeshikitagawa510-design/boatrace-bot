import os
import json
import requests
from datetime import datetime, timedelta, timezone
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
JSON_FILENAME = 'scoring_dictionary.json'

def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ DISCORD_WEBHOOK_URL が設定されていません。")
        return
    payload = {"content": message}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def main():
    print("🚀 朝の万舟チャンスレーススキャンを開始します...")
    
    if not os.path.exists(JSON_FILENAME):
        print(f"❌ {JSON_FILENAME} が見つかりません。")
        return

    with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
        scoring_dict = json.load(f)

    manshu_overall = scoring_dict.get('manshu_overall', {})
    in_tobi_overall = scoring_dict.get('in_tobi_overall', {})

    JST = timezone(timedelta(hours=+9))
    today_str = datetime.now(JST).strftime('%Y%m%d')
    
    high_score_races = []

    for jcd in range(1, 25):
        jcd_str = str(jcd).zfill(2)
        check_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={jcd_str}&hd={today_str}"
        try:
            res = cffi_requests.get(check_url, impersonate="chrome110", timeout=10)
            if "データがありません" in res.text or res.status_code != 200:
                continue
        except:
            continue

        for rno in range(1, 13):
            race_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd_str}&hd={today_str}"
            try:
                response = cffi_requests.get(race_url, impersonate="chrome110", timeout=10)
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                tbodys = soup.find_all('tbody', class_='is-fs12')
                if not tbodys or len(tbodys) < 6:
                    continue

                # 1号艇レーサー名取得
                in_name = "不明"
                name_div = tbodys[0].find('div', class_='is-fs18 is-fBold')
                if name_div and name_div.find('a'):
                    in_name = name_div.find('a').get_text(strip=True).replace(' ', '')

                # 2〜6号艇レーサー名取得
                outer_names = []
                for idx in range(1, 6):
                    n_div = tbodys[idx].find('div', class_='is-fs18 is-fBold')
                    if n_div and n_div.find('a'):
                        outer_names.append(n_div.find('a').get_text(strip=True).replace(' ', ''))

                # スコア計算
                in_tobi_score = in_tobi_overall.get(in_name, 0)
                manshu_score = sum(manshu_overall.get(name, 0) for name in outer_names)
                total_score = in_tobi_score + manshu_score

                # しきい値判定（スコア30以上を抽出）
                if total_score >= 30:
                    high_score_races.append({
                        'jcd': jcd_str,
                        'rno': rno,
                        'score': total_score,
                        'in_name': in_name
                    })
            except:
                pass

    # 通知メッセージ構築
    if high_score_races:
        # スコア順にソート
        high_score_races.sort(key=lambda x: x['score'], reverse=True)
        
        msg = f"🔥 **【本日({today_str})の万舟チャンスレース】** 🔥\n\n"
        for r in high_score_races:
            msg += f"📍 **場コード {r['jcd']} / {r['rno']}R** (スコア: **{r['score']}pt**)\n"
            msg += f" └ 1号艇: {r['in_name']}\n"
            msg += f" └ 🔗 https://www.boatrace.jp/owpc/pc/race/racelist?rno={r['rno']}&jcd={r['jcd']}&hd={today_str}\n\n"
    else:
        msg = f"📊 **【本日({today_str})の万舟チャンスレース】**\n本日は高スコア対象レースがありませんでした。"

    send_discord(msg)
    print("✅ Discord通知を送信しました。")

if __name__ == '__main__':
    main()
