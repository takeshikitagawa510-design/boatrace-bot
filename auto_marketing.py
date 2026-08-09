import os
import time
import tweepy
from google import genai
from google.genai import errors

# X API 認証
client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"]
)

# Gemini API 認証 (Tier 1 前払いキー)
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
    # サーバー一時不具合(500エラー)対策で最大3回リトライ
    for attempt in range(1, 4):
        try:
            print(f"Gemini API呼び出し試行 [{attempt}/3]...")
            response = ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            if response and response.text:
                print("Gemini AIによる文章生成成功！")
                return response.text.strip()
        except errors.APIError as e:
            print(f"Gemini APIエラー: {e.message}")
        except Exception as e:
            print(f"予期せぬエラー: {e}")
        
        # 失敗時は1秒待って再試行
        time.sleep(1)

    return None

def run_auto_post():
    post_text = generate_marketing_post()
    
    if not post_text:
        print("❌ Gemini AIによるポスト文章生成に失敗しました。")
        return

    try:
        res = client.create_tweet(text=post_text)
        print(f"[X自動投稿成功] Tweet ID: {res.data['id']}")
        print(f"投稿内容:\n{post_text}")
    except Exception as e:
        print(f"❌ [X投稿エラー]: {e}")

if __name__ == "__main__":
    run_auto_post()
