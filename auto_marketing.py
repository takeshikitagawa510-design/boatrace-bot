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

def get_all_candidate_models():
    """アカウントで利用可能な全モデル一覧を取得してリスト化"""
    candidates = []
    try:
        models = ai_client.models.list()
        for model in models:
            model_name = getattr(model, 'name', '') or str(model)
            clean_name = model_name.replace('models/', '')
            # テキスト生成系モデルを抽出
            if 'flash' in clean_name or 'pro' in clean_name:
                candidates.append(clean_name)
    except Exception as e:
        print(f"モデル一覧の取得中にエラーが発生しました: {e}")
    
    # 取得できなかった場合のバックアップ固定候補
    default_candidates = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.0-flash-lite']
    for m in default_candidates:
        if m not in candidates:
            candidates.append(m)
            
    print(f"試行対象のモデル候補リスト: {candidates}")
    return candidates

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
    candidate_models = get_all_candidate_models()

    for model_name in candidate_models:
        try:
            print(f"[{model_name}] での生成を試みます...")
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if response and response.text:
                print(f"🎉 [{model_name}] で生成に成功しました！")
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
        print("❌ 全てのモデルで文章生成に失敗したため、処理を停止しました。")
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
