"""cache_read 할인은 요청당 cache_read_input이 1024 토큰 이상일 때만 적용된다.
따라서 정적 prefix를 의도적으로 1024 토큰 이상으로 만든다. few-shot 4개가 그 역할을 한다."""

SCHEMA = """You are an English learning content generator for Korean learners.
For each input sentence, output one JSON object with these exact fields:
  "sentence"    : the original English sentence, unchanged
  "translation" : a natural Korean translation of the whole sentence
Return ONLY a JSON array, one object per input sentence, in the same order.
Do not add commentary, markdown fences, numbering, or any field not listed above.
Keep translations natural spoken Korean, not literal word-by-word renderings.
If a sentence contains a phrasal verb, translate the phrase as a unit."""

FEWSHOT = [
    ("I usually feel tired after work.", "나는 보통 퇴근 후에 피곤함을 느껴."),
    ("I can't figure out what's causing it.", "무엇이 그걸 유발하는지 알아낼 수가 없어."),
    ("Not really. I might just stay home and relax.", "별로. 그냥 집에서 쉴까 싶어."),
    ("Sorry I'm late, the traffic was terrible today.", "늦어서 미안해, 오늘 교통이 정말 최악이었어."),
    ("Would you like that with oat milk or regular?", "오트밀크로 드릴까요, 아니면 일반 우유로 드릴까요?"),
    ("That happens a lot around this time, doesn't it?", "이맘때면 자주 그러지, 그렇지 않아?"),
]

def build_static_prefix() -> str:
    ex = "\n\n".join(
        f'Example {i}:\nInput: {s}\nOutput: {{"sentence": "{s}", "translation": "{k}"}}'
        for i, (s, k) in enumerate(FEWSHOT, 1))
    guidance = """
Quality rules for every translation:
- Preserve the meaning, tense, speaker intention, and level of certainty.
- Use a natural Korean sentence that a learner would actually hear in conversation.
- Keep names, numbers, time expressions, and concrete objects accurate.
- Translate common phrasal verbs as one unit: figure out means 알아내다, stay home means 집에 있다,
  look at means 살펴보다, count me in means 나도 함께할게.
- Do not invent a subject, event, emotion, or reason that is absent from the English sentence.
- Keep contractions and conversational tone natural in Korean.
- If the sentence is a question, preserve the question form and politeness.
- If the sentence is a response, preserve whether it agrees, refuses, confirms, or changes topic.
- Output one object for every input line and preserve the input order exactly.
- Copy each original sentence character-for-character into the sentence field.
- Never output a blank, a null value, a markdown fence, or explanatory prose.

The generated exercises are used by an English learner. A good translation is short enough to read on
a phone, faithful enough to teach vocabulary, and natural enough to say aloud. Prefer ordinary spoken
Korean over dictionary glosses. For example, “I barely have energy to cook dinner” should communicate
that the speaker has almost no energy left, not merely that cooking dinner is difficult. “That sounds
great, count me in” should communicate enthusiastic participation. “I was about to when you called”
should preserve the interrupted intention and past timing. These examples define the quality bar for
all outputs, even when a sentence is not included in the worked examples above.

Additional translation checks: distinguish “not yet” from “never”; distinguish “might” from a firm
plan; distinguish “should” advice from a command; preserve whether “barely” means almost not at all;
preserve “already”, “still”, “just”, “yet”, and “until” whenever they appear. Keep the learner-facing
translation free of academic terminology. “I figured something happened” is a natural inference,
not a statement that the speaker calculated a number. “No rush” is reassurance that there is no need
to hurry. “Would you like that with oat milk or regular?” is a service interaction, so Korean honorifics
are appropriate. “I’ll just find a seat” expresses a small, immediate action and should remain casual.
When an English sentence has an idiom or phrasal verb, translate its meaning in context rather than
translating each word independently. These rules are part of the fixed generator contract and must be
followed for every batch request.
"""
    return f"{SCHEMA}\n\nWorked examples:\n\n{ex}\n{guidance}\nNow process the input sentences below."

if __name__ == "__main__":
    p = build_static_prefix()
    print(f"chars={len(p)}  approx_tokens={len(p)//4}")
    assert len(p) // 4 >= 1024, "정적 prefix가 1024 토큰 미만이면 캐시 할인이 0이다. few-shot을 더 추가하라."
