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

def generate_marketing_post():
    prompt = """
あなたは競艇AI「NEXUS-X」の個人開発者（エンジニア）です。
X（Twitter）で競艇ファンの「いいね」や「リポスト（RT）」を爆発させるための、リアルな独り言ポスト（130文字以内）を1つ作成してください。

【厳格な禁止事項（絶対遵守）】
・Discordやサイトへの誘導（URLや「Discordはこちら」などの宣伝文句）は【1文字も】入れないでください。
・ハッシュタグ（#競艇 など）は一切付けないでください。
・「〜しましょう」「〜が鉄則です」といった教訓・説教トーンは禁止です。
・絵文字の多用は禁止（使うなら1個まで）。

【テーマ（以下のいずれか1つを深掘りする）】
・一般ファンがハマっている「展示タイムの罠」や「オッズ過剰集中」のデータ指摘
・過去10万レースのデータを分析していて気づいた、競艇場や艇ごとの露骨な傾向
・感情や予想を捨てて「期待値（EV）」だけ追うことの数学的な合理性

【トーン＆マナー】
・「〜なんだよね」「〜だわ」「〜すぎる」「〜で草」など、開発者がリアルにXで呟いている人間味のあるトーン。
・130文字前後で、読んだ人が「へぇ〜」「確かに」と思わずリポストしたくなる分析オタク感を出してください。
"""
    # 混雑時に順次試すモデル候補
    candidate_models = ['gemini-flash-latest', 'gemini-pro-latest']

    for model_name in candidate_models:
        for attempt in range(3):
            try:
                print(f"🔄 文章生成を試行中... (モデル: {model_name} / 試行回数: {attempt + 1})")
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"⚠️ APIレスポンス待機/エラー ({model_name}): {e}")
                time.sleep(5)  # 混雑時は5秒待って再試行

    print("❌ すべての候補モデルで生成に失敗しました。")
    return None

def run_auto_post():
    # 🤖 0〜480分（0〜8時間）の範囲でランダム待機し、12:00〜20:00の間に投稿
    delay_seconds = random.randint(0, 28800)
    delay_minutes = round(delay_seconds / 60, 1)
    print(f"⏳ 12:00〜20:00のランダム投稿のため、{delay_minutes} 分間待機します...")
    time.sleep(delay_seconds)

    print("📝 文章生成を開始します...")
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
