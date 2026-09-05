import os
import time
import random
import tweepy
from google import genai

# X API (v2) 認証
client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"]
)

# Gemini API 認証
ai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 競艇ファンがブックマークしたくなるデータ分析テーマ群
VIRAL_DATA_THEMES = [
    "【戸田・平和島のイン飛び条件】狭水面や潮・風の影響で、1号艇が展示1位でもオッズ過剰で期待値がマイナスになる具体的なパターン。",
    "【展示タイムと周り足の乖離】直線タイム最速にオッズが集中した際、展示3〜4位で周り足指数が高い艇を拾うモデルの回収率傾向。",
    "【風速5m以上のオッズ歪み】向かい風・追い風が強まった際のセオリー崩れと、市場オッズが追いついていない艇番のデータ傾向。",
    "【期待値（EV）運用の冷徹な事実】的中率70%の堅い買い目より、的中率15%でオッズが歪んだ中穴を買い続ける方が数理的に資産が残る理由。",
    "【チルト角・モーター補正の盲点】モーター2連率の数字に惑わされるファン心理と、直近節の整備傾向を特徴量に入れた時のデータ変化。"
]

def generate_marketing_post():
    theme = random.choice(VIRAL_DATA_THEMES)

    prompt = f"""
あなたは競艇データ分析AI「NEXUS-X」を運用するエンジニアです。
X（Twitter）で競艇ファンの「ブックマーク（保存）」と「プロフィール閲覧」を最大化するポストを作成してください。

【今回のデータ考察テーマ】
{theme}

【厳格な生成ルール】
1. 文字数は80〜115文字以内。長文や日記調は禁止。
2. 1行目は「〜のデータ見てて思うけど」「ぶっちゃけ〜」など、タイムラインで指を止める書き出しにする。
3. 文末は必ず「（検証条件や生データはプロフにまとめてる）」または「（バックテストの詳細はプロフに記載）」のニュアンスで自然に締めること。
4. URLやハッシュタグ（#競艇等）は直接貼らないこと。
5. 「目がシパシパ」「仮眠」「頑張った」などの開発者ポエム、および「〜で草」「罠なんだわ」等の安っぽいスラングは完全禁止。無骨で知的なエンジニアトーンを維持する。
6. 本文のみを出力すること。
"""

    candidate_models = ['gemini-flash-latest', 'gemini-pro-latest']

    for model_name in candidate_models:
        for attempt in range(3):
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                time.sleep(5)

    return None

def run_auto_post():
    # 12:00〜20:00の間にランダム投稿
    delay_seconds = random.randint(0, 28800)
    delay_minutes = round(delay_seconds / 60, 1)
    print(f"⏳ 12:00〜20:00のランダム投稿のため、{delay_minutes} 分間待機します...")
    time.sleep(delay_seconds)

    print("📝 文章生成を開始します...")
    post_text = generate_marketing_post()
    
    if not post_text:
        print("❌ AIの文章生成に失敗したため処理を中断します。")
        return

    print(f"\n--- [生成された投稿文] ---\n{post_text}\n---------------------------\n")

    try:
        res = client.create_tweet(text=post_text)
        print(f"🎉 [X自動投稿成功] Tweet ID: {res.data['id']}")
    except Exception as e:
        print(f"❌ [X投稿失敗]: {e}")
        raise e

if __name__ == "__main__":
    run_auto_post()
