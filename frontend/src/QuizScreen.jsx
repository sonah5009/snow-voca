import { useEffect, useState } from "react";
import { fetchNextExercise, submitAnswer } from "./api.js";
import { useSpeechInput } from "./useSpeechInput.js";

export default function QuizScreen() {
  const [exercise, setExercise] = useState(null);
  const [result, setResult] = useState(null);
  const { listening, transcript, start, supported } = useSpeechInput();
  const [manualInput, setManualInput] = useState("");

  const loadNext = () => {
    setResult(null);
    setManualInput("");
    fetchNextExercise()
      .then(setExercise)
      .catch(() => setExercise(null));
  };

  useEffect(loadNext, []);

  useEffect(() => {
    if (transcript) submit(transcript);
  }, [transcript]);

  const submit = async (spokenText) => {
    if (!exercise) return;
    const res = await submitAnswer(exercise.id, spokenText);
    setResult({ ...res, spokenText });
  };

  if (!exercise) {
    return <p>더 풀 문제가 없습니다. 🎉</p>;
  }

  const options = [exercise.meaning_correct, ...exercise.meaning_distractors];

  return (
    <div style={{ maxWidth: 480, margin: "0 auto", fontFamily: "sans-serif" }}>
      <h2>{exercise.sentence}</h2>

      <ul>
        {options.map((meaning) => (
          <li key={meaning}>{meaning}</li>
        ))}
      </ul>

      {supported ? (
        <button onClick={start} disabled={listening}>
          {listening ? "듣는 중..." : "🎤 답변하기"}
        </button>
      ) : (
        <div>
          <input
            value={manualInput}
            onChange={(e) => setManualInput(e.target.value)}
            placeholder="빈칸에 들어갈 단어를 입력하세요"
          />
          <button onClick={() => submit(manualInput)}>제출</button>
        </div>
      )}

      {result && (
        <div>
          <p>
            {result.correct ? "✅ 정답!" : `❌ 오답 (정답: ${result.answer})`}
          </p>
          {result.feedback && <p>{result.feedback}</p>}
          <button onClick={loadNext}>다음 문제</button>
        </div>
      )}
    </div>
  );
}
