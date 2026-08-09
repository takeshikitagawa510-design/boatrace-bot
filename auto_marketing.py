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

# Gemini API 認証
ai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def get_available_model():
    """アカウントで利用可能なテキスト生成モデルを動的に取得"""
    try:
        models = ai_client.models.list()
        for model in models:
            # モデル名を取得
            model_name = getattr(model, 'name', '') or str(model)
            # generateContent に対応しているモデルを抽出
            if 'flash' in model_name or 'pro' in model_name:
                clean_name = model_name.replace('models/', '')
                print(f"利用可能モデルを発見: {clean_name}")
                return clean_name
    except Exception as e:
        print(f"モデル一覧の取得中にエラーが発生しました: {e}")
    return None

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
    # 利用可能なモデル名を動的に取得
    target_model = get_available_model()
    
    if not target_model:
        print("利用可能なモデルが見つかりませんでした。")
        return None

    try:
        print(f"[{target_model}] を使用して生成を実行中...")
        response = ai_client.models.generate_content(
            model=target_model,
            contents=prompt
        )
        if response and response.text:
            print(f"✅ [{target_model}] での生成に成功しました。")
            return response.text.strip()
    except errors.APIError as e:
        print(f"⚠️ APIエラー (Code: {e.code}): {e.message}")
    except Exception as e:
        print(f"⚠️ エラー: {e}")

    return None

def run_auto_post():
    post_text = generate_marketing_post()
    
    if not post_text:
        print("❌ 文章生成に失敗したため、処理を停止しました。")
        raise Exception("Gemini APIからの文章取得に失敗しました。")

    try:
        res = client.create_tweet(text=post_text)
        print(f"🎉 [X自動投稿成功] Tweet ID: {res.data['id']}")
        print(f"--- 投稿内容 ---\n{post_text}\n--------------")
    except Exception as e:
        print(f"❌ [X投稿エラー]: {e}")
        raise e

if __name__ == "__main__":
    run_auto_post()
