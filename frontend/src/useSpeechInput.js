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
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      setTranscript(event.results[0][0].transcript);
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
