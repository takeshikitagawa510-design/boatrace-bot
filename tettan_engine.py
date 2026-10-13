import requests
from bs4 import BeautifulSoup
import re
import json

BASE_URL = "https://boatrace-shinsum.com"
JOKEN_URL = f"{BASE_URL}/joken/"

# 認証情報
USER_ID = "sum"
USER_PASS = "sao"

# Discord Webhook（通知先チャンネルのURLをセット）
DISCORD_WEBHOOK_URL = ""

session = requests.Session()
# Basic認証をセッションにセット
session.auth = (USER_ID, USER_PASS)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
session.headers.update(headers)

def fetch_in_high_races():
    """1. 条件ページからイン逃げ高（1着率75%以上）のレースを取得"""
    res = session.get(JOKEN_URL)
    if res.status_code != 200:
        print(f"アクセス失敗: ステータスコード {res.status_code}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    races = []

    # リンク要素の走査
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        # 勝率表記（例: 80% など）があるか判定
        match = re.search(r"(\d{2})%", text)
        if match:
            rate = int(match.group(1))
            if rate >= 75:
                full_url = BASE_URL + href if href.startswith("/") else href
                races.append({
                    "url": full_url,
                    "win_rate": rate,
                    "info": text
                })
    return races

def inspect_race(detail_url):
    """2. 各レース詳細をチェックして鉄板判定 & 買い目生成"""
    res = session.get(detail_url)
    if res.status_code != 200:
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    body = soup.get_text()

    # 判定1: 3・4号艇にスリットアラートが出ているか（壁突破リスクの検知）
    threat_outer = False
    if "スリットアラート" in body:
        # 3枠・4枠の近辺にアラート表記があるか確認
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        for line in lines:
            if any(num in line for num in ["3", "4"]) and "アラート" in line and "出ず" not in line:
                threat_outer = True
                break

    # 判定2: 軸指数の抽出（2〜6号艇）
    axis_scores = {}
    for boat in range(2, 7):
        m = re.search(rf"{boat}\s*[^\d\n]+\s*(\d{{1,3}})", body)
        axis_scores[boat] = int(m.group(1)) if m else 0

    sorted_axis = sorted(axis_scores.items(), key=lambda x: x[1], reverse=True)
    top2 = sorted_axis[0][0] if sorted_axis else 2
    top3 = sorted_axis[1][0] if len(sorted_axis) > 1 else 3
    top4 = sorted_axis[2][0] if len(sorted_axis) > 2 else 4

    # 判定3: 買い目生成（最大4点、キキさん向け厳選仕様）
    if threat_outer:
        # 外の攻め手アラートあり → 壁崩壊リスクのため見送り
        return {"status": "SKIP", "reason": "3/4枠スリットアラート検知（壁不安）"}

    # 2号艇が軸指数トップ（壁厚＆相手筆頭）
    if top2 == 2:
        picks = [
            f"1-2-{top3}",
            f"1-2-{top4}",
            f"1-2-5" if top4 != 5 and top3 != 5 else f"1-2-6"
        ]
        rank = "SS (鉄壁イン逃げ・2着固定3点)"
    else:
        # 2と3が競り合い（4点本線）
        picks = [
            f"1-2-{top2}",
            f"1-{top2}-2",
            f"1-2-{top3}",
            f"1-{top2}-{top3}"
        ]
        rank = "S (イン逃げ本線・相手競り合い4点)"

    # 重複除去
    picks = list(dict.fromkeys(picks))[:4]

    return {
        "status": "PASS",
        "rank": rank,
        "picks": picks,
        "axis_scores": axis_scores
    }

def main():
    print("=== イン逃げ鉄板スキャナー実行 ===")
    races = fetch_in_high_races()
    print(f"イン逃げ高（75%以上）対象: {len(races)}件")

    for r in races:
        result = inspect_race(r["url"])
        if not result or result.get("status") == "SKIP":
            continue

        print(f"\n【対象レース】URL: {r['url']}")
        print(f"勝率: {r['win_rate']}% | 判定: {result['rank']}")
        print(f"🎯 厳選買い目: {', '.join(result['picks'])}")

if __name__ == "__main__":
    main()
