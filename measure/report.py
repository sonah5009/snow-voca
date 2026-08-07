import json, pathlib
from collections import defaultdict

LEDGER = pathlib.Path("results/llm_calls.jsonl")

# 투영 가정 (덱에 그대로 명시한다)
CONVS_PER_RUN     = 5      # 시드 대화 5개
LEARNER_DAYS      = 5      # 대화 1개 = 학습자 1인 1일치 콘텐츠로 간주
PROJ_LEARNERS     = 1000
PROJ_DAYS         = 30

def load():
    agg = defaultdict(lambda: defaultdict(float))
    stages = defaultdict(lambda: defaultdict(float))
    for line in LEDGER.read_text().splitlines():
        r = json.loads(line)
        a = agg[r["run_label"]]
        a["calls"] += 1
        for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"):
            a[k] += r[k]
        a["usd"] += r["usd"]
        stages[r["run_label"]][r["stage"]] += r["usd"]
    return agg, stages

def main():
    agg, stages = load()
    if "naive" not in agg or "ours" not in agg:
        print("두 run이 다 있어야 한다. baseline_naive.py 와 generate_exercises.py 를 각각 1회 실행하라.")
        print("현재:", dict((k, int(v['calls'])) for k, v in agg.items()))
        return

    hdr = f"{'run':<8}{'calls':>7}{'input':>11}{'cache_rd':>11}{'output':>10}{'USD':>12}"
    print("\n" + hdr); print("-" * len(hdr))
    for label in ("naive", "ours"):
        a = agg[label]
        print(f"{label:<8}{int(a['calls']):>7}{int(a['input_tokens']):>11,}"
              f"{int(a['cache_read_tokens']):>11,}{int(a['output_tokens']):>10,}"
              f"{a['usd']:>12.4f}")
    print("-" * len(hdr))

    n, o = agg["naive"]["usd"], agg["ours"]["usd"]
    red = (n - o) / n * 100 if n else 0
    print(f"\n>>> 비용 절감률: {red:.1f}%   (${n:.4f} → ${o:.4f})\n")

    nd, od = n / LEARNER_DAYS, o / LEARNER_DAYS
    print(f"학습자 1인 1일 원가 : naive ${nd:.6f}  →  ours ${od:.6f}")
    scale = PROJ_LEARNERS * PROJ_DAYS
    print(f"{PROJ_LEARNERS:,}명 x {PROJ_DAYS}일 : naive ${nd*scale:,.2f}  →  ours ${od*scale:,.2f}"
          f"  (월 ${(nd-od)*scale:,.2f} 절감)")

    print("\n단계별 비용 (ours):")
    for s, v in sorted(stages["ours"].items(), key=lambda x: -x[1]):
        print(f"  {s:<15} ${v:.6f}")

    print("\n가정: 대화 1개 = 학습자 1인 1일치 콘텐츠. 단가는 Snowflake 공개 예시 rate 기준 추정.")

if __name__ == "__main__":
    main()
