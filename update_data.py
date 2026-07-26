import os
import re
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from datetime import datetime, timedelta, timezone

CSV_FILENAME = 'manshu_half_year_recovery.csv'
JSON_FILENAME = 'scoring_dictionary.json'
HEADER = ['日付', '場コード', 'レース', '決まり手', '3連単配当', '1着の枠', '1着(立役者)', '1枠(飛んだイン)']

print("\n🔄 【データ更新】最新結果の回収と辞書の再生成を開始します...\n")

# 1. CSVの読み込みと掃除
if os.path.exists(CSV_FILENAME):
    df_old = pd.read_csv(CSV_FILENAME, encoding='utf-8')
    df = df_old[pd.to_numeric(df_old['3連単配当'], errors='coerce') < 1000000].copy()
else:
    df = pd.DataFrame(columns=HEADER)

JST = timezone(timedelta(hours=+9))
now = datetime.now(JST)

if not df.empty:
    latest_date_str = str(int(pd.to_numeric(df['日付']).max()))
    latest_date = datetime.strptime(latest_date_str, '%Y%m%d').replace(tzinfo=JST)
else:
    latest_date = now - timedelta(days=2)

end_date = now.date() if now.hour >= 21 else (now - timedelta(days=1)).date()

target_dates = []
current_date = latest_date + timedelta(days=1)
while current_date.date() <= end_date:
    target_dates.append(current_date.strftime('%Y%m%d'))
    current_date += timedelta(days=1)

# 2. 空白期間のデータ取得
if target_dates:
    print(f"⚠️ {len(target_dates)}日分の新規データを取得します: {target_dates}")
    for date_str in target_dates:
        daily_data = []
        for jcd in range(1, 25):
            jcd_str = str(jcd).zfill(2)
            check_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd={jcd_str}&hd={date_str}"
            try:
                res = cffi_requests.get(check_url, impersonate="chrome110", timeout=10)
                if "データがありません" in res.text or res.status_code != 200: continue
            except: continue

            for rno in range(1, 13):
                res_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd_str}&hd={date_str}"
                try:
                    response = cffi_requests.get(res_url, impersonate="chrome110", timeout=10)
                    if response.status_code != 200: continue
                    soup = BeautifulSoup(response.text, 'html.parser')

                    payout = 0
                    for table in soup.find_all('table'):
                        if '3連単' in table.text and '¥' in table.text:
                            for tr in table.find_all('tr'):
                                if '3連単' in tr.text:
                                    for td in tr.find_all('td'):
                                        if '¥' in td.text:
                                            val = re.sub(r'[^\d]', '', td.text)
                                            if val: payout = int(val)

                    if payout >= 10000:
                        w_waku, w_name, in_name, kimi = "不明", "不明", "不明", "不明"
                        kimi_td = soup.find('td', class_='is-kkrm')
                        if kimi_td: kimi = kimi_td.get_text(strip=True)

                        for table in soup.find_all('table'):
                            if '着' in table.text and 'ボートレーサー' in table.text:
                                for tr in table.find_all('tr'):
                                    cols = tr.find_all('td')
                                    if len(cols) >= 3:
                                        if '1' in cols[0].text or '１' in cols[0].text:
                                            w_nums = re.findall(r'\d', cols[1].text)
                                            if w_nums: w_waku = w_nums[0]
                                            w_name = re.sub(r'^\d+', '', cols[2].text.strip().replace('\n', '').replace(' ', '').replace(' ', ''))
                                            break
                                break

                        list_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd_str}&hd={date_str}"
                        list_res = cffi_requests.get(list_url, impersonate="chrome110", timeout=10)
                        list_soup = BeautifulSoup(list_res.text, 'html.parser')
                        tbodys = list_soup.find_all('tbody', class_='is-fs12')
                        if tbodys and len(tbodys) >= 1:
                            name_div = tbodys[0].find('div', class_='is-fs18 is-fBold')
                            if name_div and name_div.find('a'):
                                in_name = re.sub(r'\s+', '', name_div.find('a').get_text(strip=True))

                        if w_waku != "1" and in_name != "不明" and w_name != "不明":
                            daily_data.append({
                                '日付': date_str, '場コード': jcd_str, 'レース': rno,
                                '決まり手': kimi, '3連単配当': payout, '1着の枠': w_waku,
                                '1着(立役者)': w_name, '1枠(飛んだイン)': in_name
                            })
                except: pass
                time.sleep(0.2)

        if daily_data:
            df_daily = pd.DataFrame(daily_data, columns=HEADER)
            df = pd.concat([df, df_daily], ignore_index=True)

    df.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')
    print("💾 CSVファイルを更新しました。")

# 3. 直近180日分から辞書 (scoring_dictionary.json) を生成
print("🧠 直近180日間のデータから辞書(JSON)を再構築中...")

df['日付_dt'] = pd.to_datetime(df['日付'].astype(str), format='%Y%m%d')
half_year_ago = now - timedelta(days=180)
df_recent = df[df['日付_dt'] >= half_year_ago]

# 万舟演出者ポイント（立役者）
manshu_counts = df_recent['1着(立役者)'].value_counts() * 10
manshu_dict = manshu_counts.to_dict()

# イン飛実績ポイント（1枠）
in_tobi_counts = df_recent['1枠(飛んだイン)'].value_counts() * 5
in_tobi_dict = in_tobi_counts.to_dict()

scoring_dict = {
    'manshu_overall': manshu_dict,
    'in_tobi_overall': in_tobi_dict
}

with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
    json.dump(scoring_dict, f, ensure_ascii=False, indent=4)

print("✨ 辞書(scoring_dictionary.json)の最新化完了！")
