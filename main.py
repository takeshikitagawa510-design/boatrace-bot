from datetime import datetime, timedelta, timezone
import json
import os
import re
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
import requests

# ==========================================
# 🎯 基本設定
# ==========================================
CHANCE_DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

JST = timezone(timedelta(hours=+9), 'JST')
TARGET_DATE = datetime.now(JST).strftime('%Y%m%d')
DISPLAY_DATE = datetime.now(JST).strftime('%Y/%m/%d')
JSON_FILENAME = 'scoring_dictionary.json'
EXCLUDE_VENUES = ['03', '04', '09']

# 💾 万舟追跡用の判定待ち保存ファイル
PICKUP_PENDING_FILE = 'pending_pickup_races.json'

VENUE_NAMES = {
    '01': '桐生',
    '02': '戸田',
    '05': '多摩川',
    '06': '浜名湖',
    '07': '蒲郡',
    '08': '常滑',
    '10': '三国',
    '11': 'びわこ',
    '12': '住之江',
    '13': '尼崎',
    '14': '鳴門',
    '15': '丸亀',
    '16': '児島',
    '17': '宮島',
    '18': '徳山',
    '19': '下関',
    '20': '若松',
    '21': '芦屋',
    '22': '福岡',
    '23': '唐津',
    '24': '大村',
}

try:
  with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
    scoring_dict = json.load(f)
except Exception:
  scoring_dict = {'manshu_overall': {}, 'in_tobi_overall': {}}


def send_discord_embed(title, description, fields, color=0xFF4500):
  """Discordへ高級感あるEmbed（カード型）メッセージを送信"""
  if not CHANCE_DISCORD_WEBHOOK_URL:
    print('⚠️ DISCORD_WEBHOOK_URL が未設定です。')
    return

  payload = {
      'embeds': [{
          'title': title,
          'description': description,
          'color': color,
          'fields': fields,
          'footer': {'text': 'NEXUS-X VIP AI Analysis Engine'},
          'timestamp': datetime.now(timezone.utc).isoformat(),
      }]
  }

  try:
    res = requests.post(CHANCE_DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    if res.status_code in [200, 204]:
      print('✅ Discord Embed送信成功！')
    else:
      print(f'⚠️ Discord送信エラー: HTTP {res.status_code}')
  except Exception as e:
    print(f'⚠️ Discord通信エラー: {e}')


# ==========================================
# 🚀 メイン解析
# ==========================================
def main():
  manshu_races = []
  pending_pickups = {}
  print(f'⚔️ 【高配当スキャナー】 {TARGET_DATE} 実行中...\n')

  for jcd in range(1, 25):
    jcd_str = f'{jcd:02d}'
    if jcd_str in EXCLUDE_VENUES or jcd_str not in VENUE_NAMES:
      continue

    check_url = f'https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={jcd_str}&hd={TARGET_DATE}'
    try:
      res = cffi_requests.get(check_url, impersonate='chrome110', timeout=5)
      if 'データがありません' in res.text:
        continue
    except:
      continue

    for rno in range(1, 13):
      try:
        list_url = f'https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd_str}&hd={TARGET_DATE}'
        response = cffi_requests.get(
            list_url, impersonate='chrome110', timeout=5
        )
        soup = BeautifulSoup(response.text, 'html.parser')
        tbodys = soup.find_all('tbody', class_='is-fs12')
        if len(tbodys) < 6:
          continue

        racers = {}
        for w, tbody in enumerate(tbodys[:6], 1):
          name_a = tbody.find('div', class_='is-fs18 is-fBold').find('a')
          name = re.sub(r'\s+', '', name_a.get_text(strip=True))
          txt = tbody.get_text(separator=' ')

          st_m = re.findall(r'(?:^|\s|[FL])\.([0-9]{2})\b', txt)
          t_sts = [float(x) / 100 for x in st_m if x.isdigit()]
          sec_st = sum(t_sts) / len(t_sts) if t_sts else 9.99

          racers[w] = {
              'name': name,
              'sec_st': sec_st,
              'has_sec': len(t_sts) > 0,
          }

        if any(not racers[w]['has_sec'] for w in range(1, 7)):
          continue
        r1 = racers[1]

        is_valid_manshu = False
        found_assassin_logs = []

        for w in range(2, 7):
          r = racers[w]
          m_pt = (
              scoring_dict.get('manshu_overall', {}).get(r['name'], 0)
          )
          if m_pt > 0 and r['sec_st'] <= 0.15:
            inner_st = racers[w - 1]['sec_st']
            if inner_st != 9.99 and (inner_st - r['sec_st']) >= 0.03:
              is_valid_manshu = True
              found_assassin_logs.append(f"🎯 {w}号艇({r['name']})")

        if is_valid_manshu:
          it = scoring_dict.get('in_tobi_overall', {}).get(r1['name'], 0)
          if it > 0:
            m_total = sum(
                scoring_dict.get('manshu_overall', {}).get(
                    racers[wk]['name'], 0
                )
                for wk in range(2, 7)
            )
            final_score = it + m_total + 30
            if final_score >= 150:
              v_name = VENUE_NAMES[jcd_str]
              manshu_races.append({
                  'v': v_name,
                  'r': rno,
                  's': final_score,
                  'targets': ' / '.join(found_assassin_logs),
                  'in_name': r1['name'],
              })

              # 💾 日中の万舟結果判定用に保存データを構築
              race_key = f'{v_name}_{rno}R'
              pending_pickups[race_key] = {
                  'v': v_name,
                  'r': rno,
                  's': final_score,
                  'jcd': jcd_str,
                  'date': TARGET_DATE,
              }
      except Exception:
        continue

  # ==========================================
  # 📡 Discord Embed送信 & 保存
  # ==========================================
  if not manshu_races:
    send_discord_embed(
        title=f'📢 本日のチャンスレース ({DISPLAY_DATE})',
        description=(
            '本日は条件を満たす高期待値レースはありませんでした。'
        ),
        fields=[],
        color=0x808080,
    )
  else:
    manshu_races.sort(key=lambda x: x['s'], reverse=True)
    fields = []
    for r in manshu_races[:15]:
      fields.append({
          'name': f"🔥 【{r['v']} {r['r']}R】 (期待値スコア: {r['s']}点)",
          'value': (
              f"└ **崩し狙い:** {r['targets']}\n└ **1号艇:** {r['in_name']}"
          ),
          'inline': False,
      })

    send_discord_embed(
        title=f'💣 本日の高回収率狙いレース ({DISPLAY_DATE})',
        description=(
            'AIスコア判定により抽出された**高波乱期待値レース**の一覧です。'
        ),
        fields=fields,
        color=0xFF4500,
    )

    # 💾 朝一の判定待ちレース一覧を「スコア上位15件」に絞り込んで自動保存
    try:
      sorted_pickups = sorted(
          pending_pickups.items(),
          key=lambda x: x[1]['s'],
          reverse=True
      )[:15]
      top15_pending_pickups = dict(sorted_pickups)

      with open(PICKUP_PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(top15_pending_pickups, f, ensure_ascii=False, indent=2)
      print(
          f'💾 万舟判定用データ（上位15件 / 全{len(pending_pickups)}件中）を保存しました。'
      )
    except Exception as e:
      print(f'⚠️ 万舟判定用データの保存エラー: {e}')


if __name__ == '__main__':
  main()
