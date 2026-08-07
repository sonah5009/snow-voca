SAMPLE_CONVERSATIONS = [
    {"id": "conv_01", "title": "Morning routine", "transcript": [
        "I usually feel tired after work.",
        "Yeah, me too. I barely have energy to cook dinner.",
        "I've been trying to go to bed earlier, but it's not working.",
        "Same here. I keep scrolling on my phone until midnight."]},
    {"id": "conv_02", "title": "Work stress", "transcript": [
        "We need to fix this bug before the deadline.",
        "I know, but I can't figure out what's causing it.",
        "Have you checked the error logs yet?",
        "Not yet, I was about to when you called.",
        "Okay, let's look at it together after lunch."]},
    {"id": "conv_03", "title": "Weekend plans", "transcript": [
        "Do you have any plans for the weekend?",
        "Not really. I might just stay home and relax.",
        "That sounds nice actually. I've been so busy lately.",
        "You should join me. We could order some food and watch a movie.",
        "That sounds great, count me in."]},
    {"id": "conv_04", "title": "Cafe order", "transcript": [
        "Can I get a medium iced latte, please?",
        "Sure, would you like that with oat milk or regular?",
        "Oat milk is fine, thanks.",
        "Alright, that'll be ready in about five minutes.",
        "No rush, I'll just find a seat."]},
    {"id": "conv_05", "title": "Traffic complaint", "transcript": [
        "Sorry I'm late, the traffic was terrible today.",
        "It's okay, I figured something happened.",
        "There was an accident on the highway, so everything just stopped.",
        "That happens a lot around this time, doesn't it?",
        "Yeah, I really should start leaving earlier."]},
]

# Naive 조건에서 프롬프트에 원본 그대로 삽입되는 학습자 시도 로그.
# Ours 조건에서는 session_cache가 숫자 3개로 압축한다. 양쪽 입력은 동일하다.
RAW_ATTEMPT_LOG = [
    {"ts": f"2026-08-0{d} 09:{m:02d}:00", "exercise_id": f"ex_{i:03d}",
     "lemma": w, "correct": c, "answer_given": a}
    for i, (d, m, w, c, a) in enumerate([
        (1, 12, "feel", True, "feel"), (1, 14, "figure", False, "figured"),
        (1, 17, "fix", True, "fix"), (1, 21, "relax", True, "relax"),
        (2, 9, "figure", False, "figure"), (2, 13, "order", True, "order"),
        (2, 15, "keep", True, "keep"), (2, 19, "stop", False, "stopped"),
        (3, 10, "join", True, "join"), (3, 12, "check", True, "check"),
        (3, 16, "figure", False, "figuring"), (3, 20, "leave", False, "leaving"),
        (4, 11, "feel", True, "feel"), (4, 15, "count", True, "count"),
        (4, 18, "happen", False, "happend"), (4, 22, "find", True, "find"),
    ], start=1)
]
