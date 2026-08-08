import os
import random
import time
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

def generate_marketing_post():
    """競艇ファンの目を引く自動投稿文をGeminiで生成"""
    prompt = """
競艇ファン（特に負けて悩んでいる人やデータ派）の興味を惹く、X（Twitter）用のポスト（120文字以内）を1つ作成してください。

【テーマの例（ランダムに意識する）】:
・展示タイムと実際の舟足のギャップ（イン飛びの危険信号）
・オッズの歪みと万舟の狙い方
・競艇で負ける人の共通パターンとデータ重視の重要性

【条件】:
・専門家っぽく落ち着いたトーン（「〜ですね」「〜が重要」など）。
・最後に自然な形で「無料DiscordでリアルタイムAIアラート配信中👇」と添える。
・ハッシュタグを2〜3個付ける（例: #競艇 #ボートレース #競艇予想 #万舟）。
・「絶対当たる」等の誇大表現は禁止。
"""
    try:
        # ★ ここを gemini-1.5-flash に修正
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Geminiポスト生成エラー: {e}")
        return None

def run_auto_post():
    """自動ポスト投稿の実行"""
    post_text = generate_marketing_post()
    if post_text:
        try:
            res = client.create_tweet(text=post_text)
            print(f"[自動投稿成功] Tweet ID: {res.data['id']}")
            print(f"投稿内容:\n{post_text}")
        except Exception as e:
            print(f"[自動投稿エラー]: {e}")

if __name__ == "__main__":
    run_auto_post()
