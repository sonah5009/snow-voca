from collections import Counter, deque


class SessionCache:
    def __init__(self):
        self.total = 0
        self.correct = 0
        self.recent = deque(maxlen=3)
        self.weak_words = Counter()

    def update(self, word: str, correct: bool):
        self.total += 1
        self.correct += int(correct)
        self.recent.append("O" if correct else "X")
        if not correct:
            self.weak_words[word] += 1

    def profile(self):
        return {
            "total": self.total,
            "correct": self.correct,
            "accuracy_rate": self.correct / self.total if self.total else 0.0,
            "recent_sequence": list(self.recent),
            "weak_word_tags": dict(self.weak_words),
        }
