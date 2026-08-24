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

# 初期フェーズに合わせた6つのバリエーション
POST_PATTERNS = [
    {
        "category": "日常（本場・観戦のリアル）",
        "instruction": "競艇場（平和島、多摩川、江戸川など）の現地飯（牛モツ、串カツ等）や、爆音を聴きながらビールを飲む空気感が最高という、1人の競艇ファンとしての素の呟き。スマホから歩きながら打ったような短く自然な文体。"
    },
    {
        "category": "日常（直感買いでの自爆）",
        "instruction": "AIのデータを無視して、自分の好きな選手のネームバリューや直感で買って綺麗に外したボヤキ。「やっぱり人間の感情で買うとろくなことにならん」という自虐・反省。"
    },
    {
        "category": "日常（開発の生々しい裏話）",
        "instruction": "週末に全24場でレースが重なり、サーバーのCPU使用率が跳ね上がってクラウド代にヒヤヒヤしている話や、深夜のコード修正で目がシパシパしているエンジニアのリアルな独り言。"
    },
    {
        "category": "バズ考察（常識破壊・議論誘発）",
        "instruction": "1行目でスクロールを止めるフックを置き、一般ファンが信じているセオリー（展示タイム最速の盲信など）の穴をデータ視点で鋭く指摘する構文。"
    },
    {
        "category": "バズ考察（特定条件のデータ暴露）",
        "instruction": "特定競艇場（戸田、鳴門、平和島など）のコース特性や、風速・チルト・周り足の組み合わせでオッズが歪むパターンを言語化する保存（ブックマーク）誘発構文。"
    },
    {
        "category": "日常（開発初期のテスト検証）",
        "instruction": "自分の作ったAIアラートのログと実際のレース結果を照らし合わせながら、ひとり晩酌しつつ『今日の精度は悪くなかったな』と淡々と手応えを感じている開発者のリアルな呟き。"
    }
]

def generate_marketing_post():
    pattern = random.choice(POST_PATTERNS)

    prompt = f"""
あなたは競艇データ分析AI「NEXUS-X」を個人開発しているエンジニア（タカ）です。
現在AIシステムをリリースしたばかりの初期フェーズです。
X（Twitter）向けに、AIが書いたと絶対にバレない「人間味と自然な空気感のあるポスト（80〜130文字）」を1つ作成してください。

【今回の投稿テーマ】: {pattern['category']}
【指示内容】: {pattern['instruction']}

【厳格な禁止ルール（絶対遵守）】
1. URL、Discordへの誘導文、ハッシュタグ（#競艇 など）は【一切入れない】。
2. 「サロン生」「コミュニティのメンバーからの声」「的中報告をもらった」など、ユーザーが存在することを前提とした捏造発言は【完全禁止】。
3. 「〜しましょう」「〜が鉄則」のような説教・教訓・上から目線トーンは禁止。
4. 「〜で草」「罠なんだわ」「未来オッズ」「リーク」などの不自然なスラング・テンプレ表現は禁止。
5. 絵文字は使わない、または文末に1個まで。

【文体ルール】
・日常系テーマの場合は、短めでスマホからパッと呟いたような飾らないトーン（「〜だな」「〜してもうた」「〜でうまい」など）。
・考察系テーマの場合は、知性的で落ち着いたデータ分析者のトーン。
・本文のみを出力してください。
"""

    candidate_models = ['gemini-flash-latest', 'gemini-pro-latest']

    for model_name in candidate_models:
        for attempt in range(3):
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                time.sleep(5)

    return None

def run_auto_post():
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
