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

def get_dynamic_theme():
    """固定文章ではなく、動的な数値や条件を混ぜたテーマを生成"""
    wind_spd = random.randint(4, 7)
    sample_count = random.randint(1500, 4800)
    samples_k = f"{sample_count:,}"

    themes = [
        f"【戸田・平和島のイン飛び】展示1位の1号艇が向かい風{wind_spd}m以上を受けた際、市場オッズが過剰人気になり期待値がマイナスに沈むデータ構造。",
        f"【展示タイムと周り足の乖離】直線タイム最速に人気が偏った際、周り足指数上位の3〜4号艇を狙うモデルの回収率傾向（直近{samples_k}走検証）。",
        f"【風速{wind_spd}m以上のオッズ歪み】強風時の外枠まくり差しにファン心理が引っ張られ、逆に過小評価される艇番と期待値の偏向。",
        "【期待値運用の冷徹な事実】的中率75%の本命買いを続けるよりも、的中率18%でオッズの歪み（期待値110%以上）だけを定額で叩く方が数理的に資金が残る理由。",
        "【モーター2連率の罠】前節の整備や部品交換（ピストン・リング・キャリアボデー）を特徴量に入れた際、表面上の2連率がどれほどノイズになるかのデータ検証。",
        f"【イン逃げ70%超えレースの落とし穴】基準勝率が高くても直前展示で気配を落とした1号艇を機械的に除外した時のROI改善率（サンプル{samples_k}件）。",
        "【2号艇の壁が崩れるサイン】2号艇の行き足が凹むパターンを事前にスリットデータで検知した際の外枠展開期待値。"
    ]
    return random.choice(themes)

def generate_marketing_post():
    theme = get_dynamic_theme()
    
    # 🎯 毎回プロフ誘導を入れるとスパム判定されるため、約25%の確率でのみ誘導を許可
    include_cta = random.random() < 0.28
    
    cta_instruction = (
        "文末に「（検証条件の詳細はプロフに記載）」または「（バックテスト結果はプロフにまとめてる）」を自然に添えること。"
        if include_cta
        else "文末のプロフィール誘導やリンク案内は一切禁止。純粋な数理的結論・考察のみで言い切って終えること。"
    )

    # 文体のバリエーションをランダム指定
    styles = [
        "淡々とデータと数理的根拠を述べるエンジニアトーン",
        "開発現場でログを見ていて気づいた独り言のようなトーン",
        "競艇ファンの常識や思い込みに疑問を投げかけるトーン"
    ]
    selected_style = random.choice(styles)

    prompt = f"""
あなたは競艇データ解析AI「NEXUS-X」のエンジニアです。
競艇ファンやデータ派が思わず納得してブックマークしたくなる短いポスト（85〜120文字）を作成してください。

【考察テーマ】
{theme}

【文体スタイル】
{selected_style}

【厳格ルール】
1. 文字数は85〜120文字以内。長文や日記調は禁止。
2. 1行目は「〜のデータ見てて思うけど」「意外と知られてないが」「直近のログ見てると」など、自然で指が止まる書き出し。
3. {cta_instruction}
4. ハッシュタグ（#競艇など）やURL、メンションは一切含めない。
5. 「目がシパシパ」「頑張った」などのポエム、「草」「罠なんだわ」等の安っぽいスラングは禁止。
6. 絵文字や感嘆符（！）は最大1個まで。落ち着いたトーンを維持する。
7. 生成したツイート本文のみを出力すること。
"""

    candidate_models = ['gemini-2.5-flash', 'gemini-1.5-flash']

    for model_name in candidate_models:
        for attempt in range(3):
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    clean_text = response.text.strip().replace('"', '').replace('「', '').replace('」', '')
                    return clean_text
            except Exception:
                time.sleep(4)

    return None

def run_auto_post():
    # 12:00〜20:00の間にランダム投稿
    delay_seconds = random.randint(0, 28800)
    delay_minutes = round(delay_seconds / 60, 1)
    print(f"⏳ ランダム投稿のため、{delay_minutes} 分間待機します...")
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
