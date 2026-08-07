import { useCallback, useRef, useState } from "react";

const ERROR_MESSAGES = {
  "not-allowed": "Microphone access is blocked. Allow it from the mic icon in the address bar.",
  "audio-capture": "No microphone found. Check that a mic is connected.",
  "no-speech": "Didn't catch anything. Tap the button and speak again.",
  network: "Speech recognition failed on the network. Check your internet connection.",
};

export function useSpeechInput() {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState(null);
  const recognitionRef = useRef(null);

  const start = useCallback(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("Web Speech API not supported in this browser");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 5;

    recognition.onresult = (event) => {
      // 인식 후보 전부를 줄바꿈으로 이어 보낸다. 채점은 후보별로 이뤄진다.
      const alternatives = Array.from(event.results[0]).map((a) => a.transcript);
      setTranscript(alternatives.join("\n"));
    };
    recognition.onerror = (event) => {
      console.error("SpeechRecognition error:", event.error);
      setError(ERROR_MESSAGES[event.error] || `Speech recognition error: ${event.error}`);
    };
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    setTranscript("");
    setError(null);
    setListening(true);
    recognition.start();
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  return { listening, transcript, error, start, stop, supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition) };
}
