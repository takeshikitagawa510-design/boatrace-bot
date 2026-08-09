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

def generate_reply_text(target_tweet_text):
    prompt = f"""
以下の競艇に関するツイートに対して、自然で共感するような返信（リプライ）文を1つ作成してください。

【対象のツイート】:
"{target_tweet_text}"

【条件】:
・60文字以内の短い文章。
・競艇好きの仲間として共感・応援するトーン（またはデータ重視の視点）。
・押し売りや宣伝っぽさを消すこと。
・「絶対当たる」「予想売ります」などのスパム的表現は禁止。
・絵文字を1〜2個使用OK。
"""
    model_name = 'gemini-flash-latest'

    try:
        response = ai_client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"❌ Gemini APIエラー: {e}")

    return None

def run_engagement():
    # 競艇関連のキーワードで直近のポストを検索
    search_query = "競艇 OR ボートレース OR 万舟 -is:retweet -is:reply"
    print(f"🔍 検索クエリ: {search_query} で最新投稿を取得中...")

    try:
        # 最新の関連ツイートを取得
        tweets = client.search_recent_tweets(
            query=search_query,
            max_results=10,
            tweet_fields=["created_at", "author_id", "text"]
        )

        if not tweets.data:
            print("該当するポストが見つかりませんでした。")
            return

        # ランダムで1つのツイートを選択してアクション
        target_tweet = random.choice(tweets.data)
        tweet_id = target_tweet.id
        tweet_text = target_tweet.text

        print(f"\n🎯 ターゲットポストを発見 [ID: {tweet_id}]:")
        print(f"「{tweet_text}」\n")

        # 1. 自動いいね
        try:
            client.like(tweet_id)
            print("❤️  [自動いいね成功]")
        except Exception as e:
            print(f"⚠️  [いいね失敗]: {e}")

        # ちょっと待機（連続操作感を消す）
        time.sleep(5)

        # 2. 自動コメント（リプライ）
        reply_text = generate_reply_text(tweet_text)
        if reply_text:
            print(f"💬 生成された返信文: {reply_text}")
            res = client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id
            )
            print(f"🎉 [自動コメント成功] Reply ID: {res.data['id']}")

    except Exception as e:
        print(f"❌ エンゲージメント処理エラー: {e}")

if __name__ == "__main__":
    run_engagement()
