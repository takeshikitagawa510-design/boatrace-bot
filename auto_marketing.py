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
あなたは競艇データ分析AI「NEXUS-X」を個人開発しているエンジニア（タカ）です。
X（Twitter）向けに、人間味と説得力のあるリアルな独り言ポスト（90〜130文字程度）を1つ作成してください。

今回は以下の【3つのパターン】の中からランダムに【どれか1つだけ】を必ず選んで書いてください：

パターンA【開発者のリアルな裏側・ボヤキ】
・バックテストの試行錯誤（未来オッズを参照してぬか喜びした、など）
・週末のサーバー負荷やクラウド代への心配
・アルゴリズム調整やバグ取りの苦労と楽しさ

パターンB【1人の競艇好きとしての素の感情】
・「AIのデータ無視して直感で買ったら綺麗に負けた（反省）」
・「昨日のレースのターン凄すぎて声出た」
・「たまには本場（競艇場）の爆音と現地飯の中でビール飲みたい」
・ユーザーから的中報告をもらって開発者冥利に尽きる話

パターンC【知的なデータ分析の発見・オタク感】
・展示タイムと市場オッズの歪みに関する客観的な分析の面白さ
・「期待値（EV）」と「回収率」の相関に関する技術的な気づき

【厳格な禁止事項（絶対遵守）】
・宣伝、URL、ハッシュタグ（#競艇 など）は【1文字も】入れないこと。
・「一般ファン」「負け組」など他者を見下す・煽るような表現は禁止。
・「〜しましょう」「〜が鉄則」といった説教・教訓トーンは禁止。
・「〜で草」「罠なんだわ」等の安っぽいネットスラング・ドヤ顔構文は禁止。
・絵文字は使う場合でも1個まで。

【トーン】
知性と親近感のある自然な開発者の独り言（「〜だな」「〜してしまった」「〜で面白い」「〜直します」など）。
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
                time.sleep(5)

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
