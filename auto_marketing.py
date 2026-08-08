import os
import tweepy

# Secretsから環境変数を取得
api_key = os.environ.get("X_API_KEY")
api_secret = os.environ.get("X_API_SECRET")
access_token = os.environ.get("X_ACCESS_TOKEN")
access_secret = os.environ.get("X_ACCESS_SECRET")

print("--- キーの存在チェック ---")
print(f"X_API_KEY: {'OK' if api_key else 'MISSING'}")
print(f"X_API_SECRET: {'OK' if api_secret else 'MISSING'}")
print(f"X_ACCESS_TOKEN: {'OK' if access_token else 'MISSING'}")
print(f"X_ACCESS_SECRET: {'OK' if access_secret else 'MISSING'}")

try:
    # API v1.1 認証テスト (アカウント認証の確認)
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api = tweepy.API(auth)
    me = api.verify_credentials()
    print(f"\n[v1.1 認証成功] アカウント名: @{me.screen_name}")
except Exception as e:
    print(f"\n[v1.1 認証失敗]: {e}")

try:
    # API v2 認証テスト (投稿・検索権限の確認)
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret
    )
    res = client.get_me()
    print(f"[v2 認証成功] アカウントID: {res.data.id}")
except Exception as e:
    print(f"[v2 認証失敗]: {e}")
