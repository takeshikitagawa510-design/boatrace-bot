import os
import random
import time
import tweepy
import openai  # pip install openai

# APIキー設定
client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"]
)
openai.api_key = os.environ["OPENAI_API_KEY"]

KEYWORDS = ["競艇 負けた", "イン飛び", "万舟 欲しい", "展示タイム"]

def generate_human_reply(tweet_text):
    """相手のツイートに合わせた『人間味のあるセンス抜群のコメント』をAIで作成"""
    prompt = f"""
以下の競艇に関する一般ユーザーのツイートに対して、自然で親しみやすい「競艇好きの個人（データ重視派）」としてリプライ（返信）を1文作成してください。

【相手のツイート】: "{tweet_text}"

【条件】:
・絵文字は1〜2個程度にし、テンションが高すぎない落ち着いたトーンにする。
・「絶対当たる」「予想売ります」「サロンへどうぞ」などの業者感・宣伝感・スパム感は完全に排除する。
・競艇好きとして共感するか、展示・データ視点の軽い一言を添える。
・30〜50文字程度の短文にする。
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # 軽量で高品質なモデル
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI生成エラー: {e}")
        return None

def run_auto_marketing():
    target_kw = random.choice(KEYWORDS)
    print(f"検索キーワード: {target_kw}")

    try:
        # 返信（reply）やリツイートを除外して検索
        tweets = client.search_recent_tweets(
            query=f"{target_kw} -is:retweet -is:reply",
            max_results=5
        )

        if not tweets.data:
            return

        for tweet in tweets.data:
            try:
                # 1. 自動いいね
                client.like(tweet.id)
                print(f"Liked: {tweet.id}")

                # 2. AIによる自然なコメント生成＆送信
                reply_text = generate_human_reply(tweet.text)
                if reply_text:
                    client.create_tweet(
                        text=reply_text,
                        in_reply_to_tweet_id=tweet.id
                    )
                    print(f"Replied: {reply_text}")

                # 人間らしさを出すランダムな待ち時間（15〜30秒）
                time.sleep(random.randint(15, 30))

            except Exception as e:
                print(f"処理スキップ/エラー: {e}")

    except Exception as e:
        print(f"APIエラー: {e}")

if __name__ == "__main__":
    run_auto_marketing()
