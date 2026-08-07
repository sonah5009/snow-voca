const BASE_URL = "http://localhost:8000";

export async function fetchNextExercise() {
  const res = await fetch(`${BASE_URL}/exercise/next`);
  if (!res.ok) throw new Error("no exercise available");
  return res.json();
}

export async function submitAnswer(exerciseId, spokenText) {
  const res = await fetch(`${BASE_URL}/exercise/${exerciseId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spoken_text: spokenText }),
  });
  return res.json();
}

export async function fetchLearnerLevel() {
  const res = await fetch(`${BASE_URL}/learner/level`);
  return res.json();
}
