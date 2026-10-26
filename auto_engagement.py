import os
import time
import random
import tweepy

# X API (v2) 認証
client = tweepy.Client(
    bearer_token=os.environ.get("X_BEARER_TOKEN"),
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_SECRET"]
)

# 💡 関心の高いユーザーを狙い撃ちするキーワード
SEARCH_QUERY = "(競艇 OR ボートレース) (展示 OR 舟足 OR オッズ OR イン飛び OR 万舟) -is:retweet -is:reply"

def run_auto_like():
    print("🔍 競艇関連ポストをスキャン中...")

    try:
        # X API仕様に準拠して10件取得
        tweets = client.search_recent_tweets(
            query=SEARCH_QUERY,
            max_results=10,
            tweet_fields=["created_at"]
        )

        if not tweets.data:
            print("スキャン結果: 該当ポストなし。")
            return

        # 取得した中からランダムで2〜3件に絞って「いいね」を実行（過剰なアクションを防止）
        target_count = min(random.randint(2, 3), len(tweets.data))
        target_tweets = random.sample(tweets.data, target_count)

        print(f"\n❤️ 【安全いいね開始】厳選した {len(target_tweets)} 件にいいねをつけます...")

        for tweet in target_tweets:
            try:
                client.like(tweet.id)
                print(f"  └ ❤️ [いいね成功] Tweet ID: {tweet.id}")
            except Exception as e:
                print(f"  └ ⚠️ [いいね失敗/スキップ]: {e}")

            # Bot判定除外のため、適度にランダムな待機時間を挟む
            time.sleep(random.uniform(2.0, 5.0))

        print("\n✨ いいね処理が正常に完了しました。")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == "__main__":
    run_auto_like()
