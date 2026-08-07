import { useEffect, useState } from "react";
import { fetchNextExercise, submitAnswer } from "./api.js";
import { useSpeechInput } from "./useSpeechInput.js";

function renderSentence(sentence) {
  const parts = sentence.split("___");
  return parts.map((part, i) => (
    <span key={i}>
      {part}
      {i < parts.length - 1 && <span className="blank">___</span>}
    </span>
  ));
}

export default function QuizScreen() {
  const [exercise, setExercise] = useState(null);
  const [result, setResult] = useState(null);
  const { listening, transcript, error, start, supported } = useSpeechInput();
  const [manualInput, setManualInput] = useState("");
  const [submitError, setSubmitError] = useState(null);

  const loadNext = () => {
    setResult(null);
    setManualInput("");
    setSubmitError(null);
    fetchNextExercise()
      .then(setExercise)
      .catch(() => setExercise(null));
  };

  useEffect(loadNext, []);

  useEffect(() => {
    if (transcript) submit(transcript);
  }, [transcript]);

  const submit = async (spokenText) => {
    const text = (spokenText || "").trim();
    if (!exercise || !text || result) return;
    try {
      const res = await submitAnswer(exercise.id, text);
      setResult({ ...res, spokenText: text });
    } catch (err) {
      // 서버 큐와 화면이 어긋난 경우. 에러 바디를 결과로 렌더링하지 말고 다시 맞춘다.
      loadNext();
      setSubmitError(`Couldn't submit (${err.message}) — reloading the exercise.`);
    }
  };

  if (!exercise) {
    return (
      <div className="quiz-card quiz-card--empty">
        <p>No more exercises. 🎉</p>
      </div>
    );
  }

  return (
    <div className="quiz-card">
      <p className="exercise-label">Exercise #{exercise.id}</p>

      <h2 className="quiz-sentence">
        “{renderSentence(exercise.sentence)}”
      </h2>

      <div className="translation-box">
        This word means{" "}
        <span className="translation-highlight">{exercise.meaning_correct}</span>
      </div>

      {supported && (
        <button
          className={`mic-button ${listening ? "mic-button--listening" : ""}`}
          onClick={start}
          disabled={listening}
        >
          🎙️ {listening ? "Listening..." : "Speak your answer"}
        </button>
      )}

      {error && <p className="mic-error">⚠️ {error}</p>}
      {submitError && <p className="mic-error">⚠️ {submitError}</p>}

      <div className="manual-input-row" style={supported ? { marginTop: 12 } : undefined}>
        <input
          value={manualInput}
          onChange={(e) => setManualInput(e.target.value)}
          placeholder="Type the word that fills the blank"
          onKeyDown={(e) => e.key === "Enter" && submit(manualInput)}
        />
        <button className="submit-button" onClick={() => submit(manualInput)}>
          Submit
        </button>
      </div>

      {result && (
        <div className={`feedback-banner ${result.correct ? "feedback-banner--correct" : "feedback-banner--wrong"}`}>
          <p className="feedback-verdict">
            {result.correct ? "✅ Correct!" : `❌ Incorrect (answer: ${result.answer})`}
          </p>
          {result.spokenText && (
            <p className="feedback-text">Heard: “{result.spokenText.split("\n")[0]}”</p>
          )}
          {result.feedback && <p className="feedback-text">{result.feedback}</p>}
          <button className="next-button" onClick={loadNext}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
