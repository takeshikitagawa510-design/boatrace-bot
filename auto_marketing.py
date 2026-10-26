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
    """兼業サラリーマン目線でのリアルな開発・運用テーマ"""
    wind_spd = random.randint(4, 7)
    sample_count = random.randint(1500, 4800)
    samples_k = f"{sample_count:,}"

    themes = [
        f"平日は仕事で展示リプレイ全部見張るの無理だから、展示タイムとスリット急変だけ拾うスクリーニングAI作って回してる。直近{samples_k}走のログ見ても、無駄打ち削って妙味レースだけ叩くのがサラリーマンの最適解な気がする。",
        f"向かい風{wind_spd}m以上のレース、展示1位のイン艇が過剰人気でオッズ吸われがち。AIでここを機械的に弾くフィルター入れたら回収の安定感が全然違う。自分で監視しなくていいのが平日は本当に助かる。",
        "アラートが鳴ったレースだけ昼休みにサッと展示見て舟券組む運用。丸乗り用の買い目配信じゃなくて、自分で見るべきレースを絞り込むための『監視カメラ』として使うのが一番しっくりきてる。",
        "競艇AI作ってて思うけど、サラリーマンに必要なのは『当たる買い目』じゃなくて『平日に全場見張る手間を肩代わりしてくれるツール』なんだよな。直前のスリット判定ロジックをもう少し詰めたい。",
        f"モーター2連率って直前の部品交換入ると一気にノイズになるから、直前展示の気配落ちを検知して通知止める仕組みを検証中（{samples_k}件バックテスト）。現場のリアルな意見聞きながら改良していきたい。",
        "締切10分前に通知来ても仕事中は展示確認バタつく問題。通知条件をもうちょい厳密に絞るか、朝の事前ピックアップと組み合わせるか悩む。同じ兼業の人たちの意見聞きながらアップデート中。"
    ]
    return random.choice(themes)

def generate_marketing_post():
    theme = get_dynamic_theme()
    
    # 🎯 毎回プロフ誘導を入れるとスパム判定されるため、約25%の確率でのみ薄く添える
    include_cta = random.random() < 0.25
    
    cta_instruction = (
        "文末に「（ツールの詳細はプロフ固定へ）」または「（開発状況はプロフにまとめてます）」を自然に添えること。"
        if include_cta
        else "文末の誘導や案内は一切不要。開発者としてのリアルな独り言・所感で自然に言い切って終えること。"
    )

    prompt = f"""
あなたは平日は会社員をしながら、競艇データ解析ツール「NEXUS-X」を自作して運用している兼業エンジニアです。
同じように「平日は仕事で忙しくて全レース見れない兼業競艇ファン」が思わず共感し、固定ポストを見に行きたくなるようなリアルなポスト（100〜130文字）を作成してください。

【ベースとなる話題・思考】
{theme}

【厳格ルール】
1. 文字数は100〜130文字以内。140文字を絶対に超えないこと。
2. 語り口調は「〜してる」「〜な気がする」「〜なんだよな」など、等身大の社会人エンジニアの落ち着いたトーン。
3. 誇大広告（「絶対勝てる」「万舟的中連発」など）や、予想屋のような売り文句は厳禁。
4. あくまで「全レース見れない自分用のスクリーニングツールを仲間と作っている」というスタンスを崩さない。
5. {cta_instruction}
6. ハッシュタグ（#競艇など）、絵文字の乱用、スラング（草、罠など）は禁止。
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
