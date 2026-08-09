import os
import time
import tweepy
from google import genai
from google.genai import errors

# X API (v2) 認証
client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"]
)

# Gemini API 認証 (前払いTier 1適用キー)
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
    # 前払いアカウントで利用可能な主要モデルIDの一覧（順に試行）
    candidate_models = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-exp',
        'gemini-1.5-flash-latest',
        'gemini-1.5-pro-latest'
    ]

    for model_name in candidate_models:
        try:
            print(f"[{model_name}] リクエスト送信中...")
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                print(f"✅ [{model_name}] で生成に成功しました！")
                return response.text.strip()
        except errors.APIError as e:
            print(f"⚠️ [{model_name}] APIエラー (Code: {e.code}): {e.message}")
        except Exception as e:
            print(f"⚠️ [{model_name}] エラー: {e}")
        
        time.sleep(1)

    return None

def run_auto_post():
    post_text = generate_marketing_post()
    
    if not post_text:
        print("❌ 全てのモデルで生成に失敗したため、処理を停止しました。")
        raise Exception("API連携またはモデル指定エラーにより投稿文章が生成されませんでした。")

    try:
        res = client.create_tweet(text=post_text)
        print(f"🎉 [X自動投稿成功] Tweet ID: {res.data['id']}")
        print(f"--- 投稿内容 ---\n{post_text}\n--------------")
    except Exception as e:
        print(f"❌ [X投稿エラー]: {e}")
        raise e

if __name__ == "__main__":
    run_auto_post()
