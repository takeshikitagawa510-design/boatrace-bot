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

# 💡 データ分析・考察コメントが刺さる「期待値の高いキーワード」
EXPERT_KEYWORDS = ["展示", "舟足", "オッズ", "買い目", "イン飛び", "進入", "モーター", "データ", "万舟"]

def generate_expert_reply(target_tweet_text):
    """プロの競艇データアナリストとして、本質的で自然なコメントを生成"""
    prompt = f"""
あなたは高度なデータ分析を行う「競艇AIアナリスト」です。
以下の競艇に関するツイートに対して、見た人が「お、この人は分かってるな」と感じるような、鋭く本質的な返信（リプライ）文を1つ作成してください。

【対象のツイート】:
"{target_tweet_text}"

【返信文の条件】:
・70文字〜100文字程度。
・単なる挨拶やお祝い・慰めは禁止。
・展示タイムと実舟足のギャップ、オッズの歪み、イン過剰人気の危険性など「プロ視点のデータ考察」を自然に1言含めること。
・上から目線にならず、知識人として落ち着いた知的なトーン。
・売り込みやDiscordリンクの添付は禁止（プロフィールへ自然に興味を持たせるため）。
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

def run_influencer_engagement():
    search_query = "(競艇 OR ボートレース) -is:retweet -is:reply"
    print("🔍 競艇関連ポストを大量スキャン中...")

    try:
        # 最新の競艇ツイートを最大10件取得
        tweets = client.search_recent_tweets(
            query=search_query,
            max_results=10,
            tweet_fields=["created_at", "public_metrics", "author_id"],
            expansions=["author_id"],
            user_fields=["public_metrics", "username", "name"]
        )

        if not tweets.data:
            print("スキャン結果: 該当ポストなし。")
            return

        users = {u.id: u for u in tweets.includes["users"]} if "users" in tweets.includes else {}

        # ----------------------------------------------------
        # 🔥 ① ヒットした全ポストに片っ端から「いいね」をつける！
        # ----------------------------------------------------
        print(f"\n❤️  【いいね祭り開始】取得した {len(tweets.data)} 件のポストにいいねをつけます...")
        
        high_value_candidates = []

        for tweet in tweets.data:
            author = users.get(tweet.author_id)
            follower_count = author.public_metrics["followers_count"] if author else 0
            tweet_likes = tweet.public_metrics.get("like_count", 0)
            text = tweet.text

            # 全件にいいね実行
            try:
                client.like(tweet.id)
                print(f"  └ ❤️ [いいね成功] ID: {tweet.id}")
            except Exception as e:
                # 既にいいね済みの場合はスキップ
                print(f"  └ ⚠️ [いいね失敗/スキップ]: {e}")

            # 連続いいねによるスパム判定（ロック）を防ぐため、1秒待機
            time.sleep(1)

            # ----------------------------------------------------
            # 🎯 ② コメント用の厳選フィルター（期待値チェック）
            # ----------------------------------------------------
            is_influential = follower_count >= 500 or tweet_likes >= 3
            has_expert_topic = any(kw in text for kw in EXPERT_KEYWORDS)

            if is_influential and has_expert_topic:
                high_value_candidates.append((tweet, author, follower_count))

        # ----------------------------------------------------
        # 💬 ③ 厳選条件に合ったポストがあれば1件だけ本質コメント送信
        # ----------------------------------------------------
        print("\n💬 【コメント判定】期待値の高いポストをチェック中...")

        if not high_value_candidates:
            print("🛑 コメント条件に合う高期待値のポストが見つからなかったため、いいねのみで終了します（無駄金防ぎ）。")
            return

        # 期待値に合う投稿の中から1つ厳選
        target_tweet, target_author, followers = random.choice(high_value_candidates)
        tweet_id = target_tweet.id
        tweet_text = target_tweet.text
        author_name = target_author.name if target_author else "不明"

        print(f"\n🎯 厳選ターゲットにコメント送信を開始します！")
        print(f"👤 投稿者: {author_name} (フォロワー: {followers}人)")
        print(f"💬 投稿内容: 「{tweet_text}」\n")

        # 本質的なAI考察コメントを生成して送信
        reply_text = generate_expert_reply(tweet_text)
        if reply_text:
            print(f"💡 AI生成された本質コメント:\n{reply_text}\n")
            res = client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id
            )
            print(f"🎉 [厳選コメント送信成功] Reply ID: {res.data['id']}")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == "__main__":
    run_influencer_engagement()
