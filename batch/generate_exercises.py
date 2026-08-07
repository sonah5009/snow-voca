import os, json, pathlib
from batch.seed_data import SAMPLE_CONVERSATIONS
from batch.static_prefix import build_static_prefix
from batch.blank_picker import pick_blank
from batch.word_cache import get_or_generate_word_metadata, hit_rate
from batch.lemma import lemmatize
from llm.client import messages, text_of, parse_json_block
from measure.meter import metered_call, COUNTERS
from common.sf import exec_sql
from dotenv import load_dotenv
load_dotenv()

CHEAP  = os.getenv("MODEL_CHEAP", "gpt-5-mini")
PREFIX = build_static_prefix()
OUT    = pathlib.Path("results/exercises.json")

def run(run_label="ours"):
    generated = []
    for conv in SAMPLE_CONVERSATIONS:                     # 22문장 → 호출 5회 (레버 5)
        body = "\n".join(f"- {s}" for s in conv["transcript"])
        blocks = [
            {"type": "text", "text": PREFIX,
             "cache_control": {"type": "ephemeral"}},      # ★ 레버 3: 여기까지 캐싱
            {"type": "text", "text": f"Input sentences:\n{body}"},
        ]
        resp = metered_call(run_label, "exercise_gen", CHEAP,
                            lambda: messages(CHEAP, blocks, max_tokens=4096,
                                             cache_key="snowvoca-exercise-gen"))
        for i, item in enumerate(parse_json_block(text_of(resp))):
            sent = item["sentence"]
            blank = pick_blank(sent)                       # 레버 1: LLM 0회
            lem = lemmatize(blank.split()[0] if " " in blank else blank)
            meta = get_or_generate_word_metadata(blank, run_label)   # 레버 2
            ex_id = f"{conv['id']}_{i:02d}"
            exec_sql("""INSERT INTO exercises
                (exercise_id, conv_id, sentence, blank_word, lemma, translation)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (ex_id, conv["id"], sent, blank, lem, item.get("translation", "")))
            generated.append({
                "id": ex_id, "conv_id": conv["id"], "sentence": sent,
                "blank_word": blank, "lemma": lem,
                "translation": item.get("translation", ""),
                "meaning_correct": meta["meaning_correct"],
                "meaning_distractors": meta["distractors"],
                "difficulty": meta["difficulty"],
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(generated, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[ours] exercises={len(generated)} cache_hit_rate={hit_rate():.1%} "
          f"llm_calls_avoided={COUNTERS['llm_calls_avoided']} -> {OUT}")

if __name__ == "__main__":
    run()
