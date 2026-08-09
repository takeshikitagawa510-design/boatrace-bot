import os
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
    prompt = """
競艇ファン（特に負けて悩んでいる人やデータ派）の興味を惹く、X（Twitter）用のポスト（120文字以内）を1つ作成してください。

【テーマ】:
・展示タイムと実際の舟足のギャップ（イン飛びの危険信号）
・オッズの歪みと万舟の狙い方
・競艇で負ける人の共通パターンとデータ重視の重要性

【条件】:
・専門家っぽく落ち着いたトーン。
・最後に「無料DiscordでリアルタイムAIアラート配信中👇」と添える。
・ハッシュタグを2〜3個付ける（例: #競艇 #ボートレース #競艇予想）。
・「絶対当たる」等の誇大表現は禁止。
"""
    model_name = 'gemini-flash-latest'

    try:
        print(f"[{model_name}] で文章を生成中...")
        response = ai_client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        if response and response.text:
            print("✅ Gemini AIによる文章生成に成功しました！")
            return response.text.strip()
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")

    return None

def run_auto_post():
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
