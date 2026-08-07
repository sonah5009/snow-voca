from batch.lemma import lemmatize
from measure.meter import COUNTERS

STOP = set("""i you he she it we they me him her us them my your his its our their
a an the this that these those and or but so if then than as at by for from in into of
on to with about after before until while is am are was were be been being do does did
not no yes very just really too also can could would should will shall may might must
have has had get got there here what when where who how do don't didn't it's i'm i've""".split())

PHRASAL = {"figure out", "look at", "count me in", "stay home", "go to bed", "wake up",
           "zoned out", "keep scrolling", "check", "leave earlier"}

def pick_blank(sentence: str) -> str:
    low = sentence.lower()
    for p in PHRASAL:
        if p in low:
            COUNTERS["llm_calls_avoided"] += 1
            return p
    words = [w.strip(".,!?\"'") for w in sentence.split()]
    cands = [w for w in words if w.lower() not in STOP and len(w) > 3]
    COUNTERS["llm_calls_avoided"] += 1        # 이 판단을 LLM에 위임하지 않았다
    if not cands:
        return max(words, key=len)
    return max(cands, key=len)                # 결정적: 가장 긴 content word
