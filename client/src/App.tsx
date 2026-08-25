import { Show, SignInButton, UserButton, useAuth } from "@clerk/react";
import { useEffect, useRef, useState } from "react";

type Mode = "dsa" | "system_design" | "behavioral" | "company";
type Company = "amazon" | "microsoft";
type Lang = "python" | "javascript" | "java" | "cpp";
type Stage = "introduction" | "technical" | "behavioral" | "closing";

interface Message {
  role: "assistant" | "user";
  content: string;
}

interface Feedback {
  overall_score?: number;
  summary?: string;
  error?: string;
  strong_points?: { title?: string; detail?: string }[];
  pain_points?: { title?: string; detail?: string }[];
  areas_of_improvement?: { title?: string; action?: string }[];
  next_steps?: string[];
}

interface User {
  id: string;
  email: string;
  name?: string;
  picture?: string;
}

interface SavedSession {
  id: string;
  mode: Mode;
  company?: string;
  role: string;
  started_at: number;
  ended_at?: number;
  has_feedback?: boolean;
}

interface SavedInterview extends SavedSession {
  transcript: Message[];
  feedback?: Feedback | null;
}

const modes: { id: Mode; icon: string; label: string; sub: string }[] = [
  { id: "dsa", icon: "⌥", label: "DSA / Coding", sub: "Algorithms & data structures" },
  { id: "system_design", icon: "◈", label: "System Design", sub: "Architecture & scalability" },
  { id: "behavioral", icon: "◎", label: "Behavioral / HR", sub: "STAR method & culture fit" },
  { id: "company", icon: "⬡", label: "Company Specific", sub: "Real interview experiences" },
];

const roles = [
  "SDE",
  "SDE-2",
  "SDE-3",
  "Frontend Engineer",
  "Backend Engineer",
  "Full Stack Engineer",
];

const languages: { id: Lang; label: string }[] = [
  { id: "python", label: "python" },
  { id: "javascript", label: "js" },
  { id: "java", label: "java" },
  { id: "cpp", label: "c++" },
];

const stages: { id: Stage; label: string }[] = [
  { id: "introduction", label: "Intro" },
  { id: "technical", label: "Technical" },
  { id: "behavioral", label: "Behavioral" },
  { id: "closing", label: "Closing" },
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const backendUrl = import.meta.env.VITE_BACKEND_URL || "";

async function readApiResponse(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      data.detail || data.message || `Request failed (${response.status})`
    );
  }
  return data;
}

function cleanTextForSpeech(text: string) {
  return text
    .replace(/```[\s\S]*?```/g, " code omitted ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!?\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/(^|\s)#{1,6}\s*/g, "$1")
    .replace(/(^|\s)[*_]{1,3}(?=\S)/g, "$1")
    .replace(/(?<=\S)[*_]{1,3}(?=\s|[.,!?;:]|$)/g, "")
    .replace(/(^|\n)\s*[-*+]\s+/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export default function App() {
  const { getToken } = useAuth();
  const [screen, setScreen] = useState<"setup" | "interview">("setup");
  const [selectedMode, setSelectedMode] = useState<Mode | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [role, setRole] = useState("SDE");
  const [resume, setResume] = useState<File | null>(null);
  const [resumeStatus, setResumeStatus] = useState("");
  const [sessions, setSessions] = useState<SavedSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  // Holds the AI response while it is being displayed progressively.
  // It is NOT added to messages until the response is completely finished.
  const [streamingMessage, setStreamingMessage] = useState("");
  const [exchangeCount, setExchangeCount] = useState(0);
  const [stage, setStage] = useState<Stage>("introduction");
  const [status, setStatus] = useState("Ready to begin");
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [currentLang, setCurrentLang] = useState<Lang>("python");
  const [code, setCode] = useState(
    "# Write your solution here\n# Explain your approach verbally first,\n# then implement it here when asked.\n\ndef solution():\n  pass"
  );
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [showFeedback, setShowFeedback] = useState(false);
  const [isSavedView, setIsSavedView] = useState(false);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  async function apiFetch(path: string, init: RequestInit = {}) {
    const token = await getToken();
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(`${backendUrl}${path}`, { ...init, headers });
  }

  useEffect(() => {
    loadAuthState();
    // Authentication functions are intentionally initialized once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessage]);

  async function loadAuthState() {
    try {
      const response = await apiFetch("/api/auth/me");
      const data = await response.json();
      const user = (data.user as User | null) || null;
      setCurrentUser(user);
      if (user) loadSavedSessions();
    } catch (error) {
      console.warn("Authentication state unavailable:", error);
    }
  }

  async function loadSavedSessions() {
    try {
      const response = await apiFetch("/api/sessions");
      if (!response.ok) return;
      const data = await response.json();
      setSessions((data.sessions as SavedSession[]) || []);
    } catch {
      // Keep setup usable if session history is unavailable.
    }
  }

  function selectMode(mode: Mode) {
    setSelectedMode(mode);
    if (mode !== "company") setSelectedCompany(null);
  }

  function selectCompany(company: Company) {
    setSelectedCompany(company);
  }

  function handleResume(file: File | null) {
    if (!file) {
      setResume(null);
      setResumeStatus("");
      return;
    }

    const allowed = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
    ];
    const extensionAllowed = /\.(pdf|docx|txt)$/i.test(file.name);

    if (
      file.size > 5 * 1024 * 1024 ||
      (!allowed.includes(file.type) && !extensionAllowed)
    ) {
      setResume(null);
      setResumeStatus("Choose a PDF, DOCX, or TXT file up to 5 MB.");
      return;
    }

    setResume(file);
    setResumeStatus(`Ready: ${file.name}`);
  }

  async function startInterview() {
    if (!selectedMode || (selectedMode === "company" && !selectedCompany)) return;

    setScreen("interview");
    setIsSavedView(false);
    setStatus("Connecting...");

    try {
      const form = new FormData();
      form.append("mode", selectedMode);
      form.append("company", selectedCompany || "");
      form.append("role", role);
      if (resume) form.append("resume", resume, resume.name);

      const res = await apiFetch("/api/start-interview", {
        method: "POST",
        body: form,
      });

      const data = await readApiResponse(res);
      if (typeof data.message !== "string" || !data.message.trim()) {
        throw new Error("The interviewer returned no opening question.");
      }

      setSessionId(data.session_id);
      await renderAIMessage(data.message);
      setStatus("Your turn — click Speak");
    } catch {
      setStatus("Connection error");
    }
  }

  async function renderAIMessage(text: string) {
    if (!text?.trim()) throw new Error("The interviewer returned an empty response.");

    const speakableText = cleanTextForSpeech(text);
    setIsSpeaking(true);
    setStreamingMessage("");

    // Keep the AI response outside `messages` while it is being displayed.
    // Previously, this function called setMessages() for every word, which
    // could create/reconcile multiple assistant bubbles and make the text
    // appear repetitive.
    const words = speakableText.split(/\s+/).filter(Boolean);
    const totalMs = Math.max(words.length * 420, 2000);
    const msPerWord = totalMs / Math.max(words.length, 1);

    // Start TTS independently so the text animation and audio can overlap.
    const audioPromise = speakText(speakableText);

    await sleep(300);

    let streamed = "";
    for (let i = 0; i < words.length; i++) {
      streamed += (i === 0 ? "" : " ") + words[i];
      setStreamingMessage(streamed);
      await sleep(msPerWord);
    }

    // Commit exactly ONE assistant message after the complete response has
    // been displayed. This prevents duplicate/repetitive chat bubbles.
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: text },
    ]);
    setStreamingMessage("");

    await audioPromise;
    setIsSpeaking(false);
  }

  async function speakText(text: string) {
    try {
      const res = await apiFetch("/api/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (res.status === 503) {
        return new Promise<void>((resolve) => {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.rate = 0.92;
          utterance.pitch = 0.95;
          const voices = window.speechSynthesis.getVoices();
          const voice = voices.find(
            (v) =>
              v.name.includes("Daniel") ||
              v.name.includes("Alex") ||
              v.name.includes("Male")
          );
          if (voice) utterance.voice = voice;
          utterance.onend = () => resolve();
          utterance.onerror = () => resolve();
          speechRef.current = utterance;
          window.speechSynthesis.speak(utterance);
        });
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Speech synthesis failed (${res.status})`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      await audio.play();

      return new Promise<void>((resolve) => {
        audio.onended = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
          resolve();
        };
      });
    } catch (error) {
      console.warn("TTS:", error);
    }
  }

  function stopCurrentSpeech() {
    audioRef.current?.pause();
    audioRef.current = null;
    window.speechSynthesis.cancel();
    speechRef.current = null;
    setIsSpeaking(false);
  }

  async function toggleRecording() {
    if (isSpeaking) stopCurrentSpeech();
    if (isRecording) stopRecording();
    else startRecording();
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => audioChunksRef.current.push(e.data);
      recorder.onstop = processAudio;
      recorder.start();

      setIsRecording(true);
      setStatus("Listening...");
    } catch {
      setStatus("Microphone access denied");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || !isRecording) return;

    recorder.stop();
    recorder.stream.getTracks().forEach((track) => track.stop());
    setIsRecording(false);
    setStatus("Processing...");
  }

  async function processAudio() {
    const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
    const fd = new FormData();
    fd.append("audio", blob, "rec.webm");

    try {
      const tr = await apiFetch("/api/transcribe", { method: "POST", body: fd });
      const td = await readApiResponse(tr);

      if (!td.text?.trim()) {
        setStatus("Nothing detected — try again");
        return;
      }

      addUserMessage(td.text);
      setStatus("Interviewer is thinking...");

      const rr = await apiFetch("/api/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: td.text,
          code: "",
        }),
      });

      const rd = await readApiResponse(rr);
      if (!rd.message?.trim()) throw new Error("The interviewer returned no response.");

      setStage(rd.stage);
      setExchangeCount(rd.exchange_count);
      await renderAIMessage(rd.message);

      if (rd.exchange_count >= 12) {
        setStatus("Interview complete 🎉");
      } else {
        setStatus("Your turn — click Speak");
      }
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  function addUserMessage(text: string) {
    setMessages((prev) => [...prev, { role: "user", content: text }]);
  }

  async function submitCode() {
    const trimmed = code.trim();
    if (!trimmed || !sessionId) return;

    const msg = `I've written my ${currentLang} solution. Please review it.`;
    addUserMessage(
      `${msg}\n\n\`\`\`\n${trimmed.substring(0, 80)}${trimmed.length > 80 ? "..." : ""
      }\n\`\`\``
    );
    setStatus("Sending code...");

    try {
      const rr = await apiFetch("/api/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: msg, code: trimmed }),
      });

      const rd = await readApiResponse(rr);
      if (!rd.message?.trim()) throw new Error("The interviewer returned no response.");

      setStage(rd.stage);
      setExchangeCount(rd.exchange_count);
      await renderAIMessage(rd.message);
      setStatus("Your turn — click Speak");
    } catch (e) {
      setStatus(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function viewSavedSession(interviewId: string) {
    try {
      const response = await apiFetch(`/api/sessions/${encodeURIComponent(interviewId)}`);
      if (!response.ok) return;

      const interview = (await response.json()) as SavedInterview;
      setSelectedMode(interview.mode);
      setSelectedCompany(
        interview.company === "amazon" || interview.company === "microsoft"
          ? interview.company
          : null
      );
      setRole(interview.role);
      setSessionId(interview.id);
      setExchangeCount(interview.transcript?.length || 0);
      setMessages(
        (interview.transcript || []).map((message: Message) => ({
          role: message.role === "assistant" ? "assistant" : "user",
          content: message.content,
        }))
      );
      setIsSavedView(true);
      setScreen("interview");
      setStatus("Saved interview");
    } catch {
      setStatus("Unable to load saved interview");
    }
  }

  async function endAndGetFeedback() {
    if (!sessionId) return;

    setStatus("Preparing your feedback...");

    try {
      const response = await apiFetch("/api/end-interview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });

      const data = await readApiResponse(response);
      setFeedback(data.feedback || {});
      setShowFeedback(true);
      setStatus("Interview complete");
    } catch (error) {
      setStatus(`Feedback error: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  function resetInterview() {
    stopCurrentSpeech();
    setShowFeedback(false);
    setScreen("setup");
    setSessionId(null);
    setMessages([]);
    setStreamingMessage("");
    setExchangeCount(0);
    setSelectedMode(null);
    setSelectedCompany(null);
    setIsSavedView(false);
    setStatus("Ready to begin");
    setCode(
      "# Write your solution here\n# Explain your approach verbally first,\n# then implement it here when asked.\n\ndef solution():\n  pass"
    );
    loadSavedSessions();
  }

  const roleLabel = role.includes("—")
    ? role
    : roles.includes(role)
      ? ({
        SDE: "SDE — Software Development Engineer",
        "SDE-2": "SDE-2 — Senior Engineer",
        "SDE-3": "SDE-3 — Staff Engineer",
      } as Record<string, string>)[role] || role
      : role;

  return (
    <>
      <Show when="signed-in">
        <div className="min-h-screen overflow-x-hidden bg-[#f4efe9] text-[#2c211e] font-sans">
          <style>{`
        @keyframes livepulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        @keyframes msgIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        @keyframes soundbar { 0%,100%{transform:scaleY(.4)} 50%{transform:scaleY(1)} }
        @keyframes recpulse { 0%,100%{box-shadow:0 0 0 0 rgba(189,48,40,.2)} 50%{box-shadow:0 0 0 6px rgba(189,48,40,0)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:translateY(0)} }
        .nofox-scroll::-webkit-scrollbar{width:3px}
        .nofox-scroll::-webkit-scrollbar-thumb{background:rgba(73,38,31,.14);border-radius:3px}
        .fade-up{animation:fadeUp .5s ease}
        .message-in{animation:msgIn .3s ease}
      `}</style>

          <nav className="fixed inset-x-0 top-0 z-100 flex items-center justify-between border-b border-[rgba(73,38,31,.14)] bg-[rgba(244,239,233,.92)] px-4 py-4 backdrop-blur-xl sm:px-8">
            <div className="flex items-center gap-2.5 text-base font-semibold tracking-tight">
              <span className="h-2 w-2 rounded-full bg-[#bd3028] shadow-[0_0_10px_rgba(189,48,40,.14)]" />
              NoFoxAI : No Fox Given
            </div>

            <div className="flex items-center gap-1.5 sm:gap-2">
              <div className="rounded-full border border-[rgba(73,38,31,.14)] bg-[#fffaf5] px-2.5 py-1 text-xs text-[#67534d] sm:px-3.5">
                {selectedMode || "—"}
              </div>
              {screen === "interview" && (
                <div className="rounded-full border border-[rgba(46,118,88,.25)] bg-[rgba(46,118,88,.08)] px-2.5 py-1 text-xs font-medium text-[#2e7658]">
                  <span className="mr-1 animate-[livepulse_2s_infinite]">●</span>
                  Live
                </div>
              )}
              <div className="hidden items-center gap-2 sm:flex">
                {currentUser && (
                  <span className="text-xs text-[#67534d]">
                    {currentUser.name || currentUser.email}
                  </span>
                )}
                <a
                  // href={currentUser ? "#" : "/auth/login"}
                  // onClick={async (e) => {
                  //   if (!currentUser) return;
                  //   e.preventDefault();
                  //   await fetch("http://localhost:7860/auth/logout", { method: "POST" });
                  //   window.location.reload();
                  // }}
                  className="rounded-lg border border-[rgba(73,38,31,.14)] bg-[#fffaf5] px-3 py-1.5 text-xs text-[#67534d] transition hover:border-[rgba(189,48,40,.45)] hover:text-[#bd3028]"
                >
                  <UserButton />
                </a>
              </div>
            </div>
          </nav>

          <main className="relative z-10 min-h-screen pt-17.5">
            {screen === "setup" && (
              <section className="flex min-h-[calc(100vh-70px)] items-center justify-center px-5 py-10">
                <div className="w-full max-w-130 fade-up">
                  <div className="mb-10 text-center">
                    <h1 className="mb-2.5 text-[2rem] font-light leading-tight tracking-[-.04em] sm:text-[2.4rem]">
                      Practice with
                      <br />
                      <strong className="bg-linear-to-br from-[#bd3028] to-[#8f211f] bg-clip-text font-semibold text-transparent">
                        real confidence
                      </strong>
                    </h1>
                    <p className="text-[.95rem] font-light text-[#67534d]">
                      AI-powered voice interviews modelled based on real experiences
                    </p>
                  </div>

                  <div className="mb-4 rounded-[20px] border border-[rgba(73,38,31,.14)] bg-[#fffaf5] p-5 shadow-[0_18px_50px_rgba(73,38,31,.08)] sm:p-7">
                    <div className="mb-3.5 text-[.7rem] font-semibold uppercase tracking-[.12em] text-[#977c73]">
                      Interview Type
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      {modes.map((mode) => (
                        <button
                          key={mode.id}
                          onClick={() => selectMode(mode.id)}
                          className={`rounded-xl border p-3.5 text-left transition ${selectedMode === mode.id
                            ? "border-[rgba(189,48,40,.45)] bg-[rgba(189,48,40,.06)] text-[#bd3028]"
                            : "border-[rgba(73,38,31,.14)] bg-[#f4efe9] text-[#67534d] hover:border-[rgba(73,38,31,.25)] hover:text-[#2c211e]"
                            }`}
                        >
                          <span className="mb-2 block text-[1.4rem]">{mode.icon}</span>
                          <div className="text-sm font-medium">{mode.label}</div>
                          <div className="mt-0.5 text-[.72rem] text-[#977c73]">{mode.sub}</div>
                        </button>
                      ))}
                    </div>

                    {selectedMode === "company" && (
                      <div className="mt-3.5">
                        <div className="mb-3.5 mt-4 text-[.7rem] font-semibold uppercase tracking-[.12em] text-[#977c73]">
                          Company
                        </div>

                        <div className="mb-3 grid grid-cols-2 gap-2">
                          {(["amazon", "microsoft"] as Company[]).map((company) => (
                            <button
                              key={company}
                              onClick={() => selectCompany(company)}
                              className={`rounded-xl border p-3.5 text-center text-sm font-medium capitalize transition ${selectedCompany === company
                                ? "border-[rgba(170,107,36,.5)] bg-[rgba(170,107,36,.06)] text-[#aa6b24]"
                                : "border-[rgba(73,38,31,.14)] bg-[#f4efe9] text-[#67534d] hover:border-[rgba(170,107,36,.3)]"
                                }`}
                            >
                              {company}
                            </button>
                          ))}
                        </div>

                        <div className="mb-2.5 text-[.7rem] font-semibold uppercase tracking-[.12em] text-[#977c73]">
                          Role
                        </div>
                        <select
                          value={role}
                          onChange={(e) => setRole(e.target.value)}
                          className="w-full appearance-none rounded-[10px] border border-[rgba(73,38,31,.14)] bg-[#f4efe9] px-3.5 py-2.5 text-sm text-[#2c211e] outline-none focus:border-[rgba(189,48,40,.45)]"
                        >
                          {roles.map((r) => (
                            <option key={r} value={r}>
                              {r === "SDE"
                                ? "SDE — Software Development Engineer"
                                : r === "SDE-2"
                                  ? "SDE-2 — Senior Engineer"
                                  : r === "SDE-3"
                                    ? "SDE-3 — Staff Engineer"
                                    : r}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <div className="mt-4.5 border-t border-[rgba(73,38,31,.14)] pt-4.5">
                      <div className="mb-2.5 text-[.7rem] font-semibold uppercase tracking-[.12em] text-[#977c73]">
                        Optional resume context
                      </div>
                      <input
                        type="file"
                        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                        onChange={(e) => handleResume(e.target.files?.[0] || null)}
                        className="w-full rounded-[10px] border border-dashed border-[rgba(189,48,40,.35)] bg-[rgba(189,48,40,.04)] p-3 text-sm text-[#67534d] file:mr-2.5 file:rounded-lg file:border-0 file:bg-[#bd3028] file:px-2.5 file:py-1.5 file:text-sm file:text-[#fffaf5]"
                      />
                      <div className="mt-1.5 text-[.72rem] leading-normal text-[#977c73]">
                        PDF, DOCX, or TXT · up to 5 MB. Alex will use your projects and
                        experience for sharper introduction questions.
                      </div>
                      <div className="mt-1.5 min-h-[1.1em] text-xs text-[#2e7658]">
                        {resumeStatus}
                      </div>
                    </div>

                    {currentUser && (
                      <div className="mt-5 border-t border-[rgba(73,38,31,.14)] pt-4.5">
                        <div className="mb-3.5 text-[.7rem] font-semibold uppercase tracking-[.12em] text-[#977c73]">
                          Saved interviews
                        </div>
                        <div className="nofox-scroll grid max-h-45 gap-2 overflow-y-auto">
                          {!sessions.length ? (
                            <div className="text-xs text-[#977c73]">No saved interviews yet.</div>
                          ) : (
                            sessions.map((item) => (
                              <div
                                key={item.id}
                                className="flex items-center justify-between gap-2.5 rounded-lg border border-[rgba(73,38,31,.14)] bg-[#f4efe9] px-3 py-2.5 text-xs text-[#67534d]"
                              >
                                <span>
                                  {item.mode}
                                  {item.company ? ` · ${item.company}` : ""} ·{" "}
                                  {new Date(item.started_at * 1000).toLocaleDateString()}
                                </span>
                                <button
                                  onClick={() => viewSavedSession(item.id)}
                                  className="text-xs text-[#bd3028]"
                                >
                                  View
                                </button>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  <button
                    onClick={startInterview}
                    disabled={!selectedMode || (selectedMode === "company" && !selectedCompany)}
                    className="w-full rounded-[14px] bg-linear-to-br from-[#c23b31] to-[#8f211f] p-4 text-[.95rem] font-semibold text-white shadow-[0_10px_24px_rgba(141,32,29,.18)] transition hover:-translate-y-px hover:shadow-[0_12px_28px_rgba(141,32,29,.25)] disabled:cursor-not-allowed disabled:opacity-35"
                  >
                    Begin Interview →
                  </button>
                </div>
              </section>
            )}

            {screen === "interview" && (
              <section className="flex h-[calc(100vh-70px)] flex-col gap-4 p-4 sm:p-5 sm:px-6">
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {[
                    ["Mode", selectedMode || "—"],
                    ["Company", selectedCompany || "N/A"],
                    ["Role", roleLabel],
                    ["Q", String(exchangeCount)],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-full border border-[rgba(73,38,31,.14)] bg-[#fffaf5] px-3 py-1 text-[.72rem] text-[#67534d]"
                    >
                      {label}
                      <span className="ml-1 text-[#2c211e]">{value}</span>
                    </div>
                  ))}

                  <div className="ml-auto flex gap-1.5">
                    {stages.map((s, i) => {
                      const stageIndex = stages.findIndex((x) => x.id === stage);
                      const cls =
                        s.id === stage
                          ? "border-[rgba(189,48,40,.45)] bg-[rgba(189,48,40,.08)] text-[#bd3028]"
                          : stageIndex > i
                            ? "border-[rgba(46,118,88,.3)] bg-[rgba(46,118,88,.06)] text-[#2e7658]"
                            : "border-[rgba(73,38,31,.14)] bg-[#fffaf5] text-[#977c73]";
                      return (
                        <div
                          key={s.id}
                          className={`rounded-full border px-2.5 py-1 text-[.68rem] font-medium ${cls}`}
                        >
                          {s.label}
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="flex min-h-0 flex-col overflow-hidden rounded-[20px] border border-[rgba(73,38,31,.14)] bg-[#fffaf5] shadow-[0_18px_50px_rgba(73,38,31,.08)]">
                    <div className="flex shrink-0 items-center gap-2 border-b border-[rgba(73,38,31,.14)] px-4.5 py-3.5 text-xs font-medium text-[#67534d]">
                      <span className="h-1.5 w-1.5 rounded-full bg-[#bd3028]" />
                      Conversation
                    </div>

                    <div className="nofox-scroll flex flex-1 flex-col gap-5 overflow-y-auto p-5">
                      {messages.map((message, index) => (
                        <div
                          key={index}
                          className={`message-in flex gap-3 ${message.role === "user" ? "flex-row-reverse" : ""
                            }`}
                        >
                          <div
                            className={`flex h-7.5 w-7.5 shrink-0 items-center justify-center rounded-full border text-xs ${message.role === "assistant"
                              ? "border-[rgba(189,48,40,.2)] bg-[rgba(189,48,40,.08)]"
                              : "border-[rgba(46,118,88,.2)] bg-[rgba(46,118,88,.08)]"
                              }`}
                          >
                            {message.role === "assistant" ? "🤖" : "👤"}
                          </div>
                          <div className="max-w-[82%]">
                            <div
                              className={`mb-1 text-[.68rem] font-semibold uppercase tracking-[.06em] text-[#977c73] ${message.role === "user" ? "text-right" : ""
                                }`}
                            >
                              {message.role === "assistant" ? "Interviewer" : "You"}
                            </div>
                            <div
                              className={`whitespace-pre-wrap rounded-[14px] px-4 py-3 text-sm font-light leading-[1.65] ${message.role === "assistant"
                                ? "rounded-tl border border-[rgba(73,38,31,.14)] bg-[#f0e7df]"
                                : "rounded-tr border border-[rgba(189,48,40,.2)] bg-[rgba(189,48,40,.08)] text-right"
                                }`}
                            >
                              {message.content}
                            </div>
                          </div>
                        </div>
                      ))}
                      {streamingMessage && (
                        <div className="message-in flex gap-3">
                          <div className="flex h-7.5 w-7.5 shrink-0 items-center justify-center rounded-full border border-[rgba(189,48,40,.2)] bg-[rgba(189,48,40,.08)] text-xs">
                            🤖
                          </div>
                          <div className="max-w-[82%]">
                            <div className="mb-1 text-[.68rem] font-semibold uppercase tracking-[.06em] text-[#977c73]">
                              Interviewer
                            </div>
                            <div className="whitespace-pre-wrap rounded-[14px] rounded-tl border border-[rgba(73,38,31,.14)] bg-[#f0e7df] px-4 py-3 text-sm font-light leading-[1.65]">
                              {streamingMessage}
                            </div>
                            {isSpeaking && (
                              <div className="mt-2 flex items-center gap-0.75 rounded-[14px] border border-[rgba(73,38,31,.14)] bg-[#f0e7df] px-3.5 py-2.5 w-fit">
                                {[8, 14, 10, 16, 8].map((h, i) => (
                                  <span
                                    key={i}
                                    className="w-0.75 rounded-full bg-[#bd3028] animate-[soundbar_1s_infinite_ease-in-out]"
                                    style={{
                                      height: h,
                                      animationDelay: `${i * 0.05}s`,
                                    }}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                      <div ref={messagesEndRef} />
                    </div>

                    <div className="flex shrink-0 items-center gap-2.5 border-t border-[rgba(73,38,31,.14)] p-3.5">
                      <button
                        disabled={isSavedView}
                        onClick={toggleRecording}
                        className={`flex shrink-0 items-center gap-2 rounded-[10px] border px-4.5 py-2.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-35 ${isRecording
                          ? "border-[rgba(189,48,40,.4)] bg-[rgba(189,48,40,.1)] text-[#bd3028] animate-[recpulse_1.5s_infinite]"
                          : "border-[rgba(189,48,40,.26)] bg-[rgba(189,48,40,.07)] text-[#bd3028] hover:bg-[rgba(189,48,40,.13)]"
                          }`}
                      >
                        <span>{isRecording ? "⏹" : "🎤"}</span>
                        <span>{isRecording ? "Stop" : "Speak"}</span>
                      </button>

                      <div className="flex-1 text-xs italic text-[#977c73]">{status}</div>

                      <button
                        disabled={isSavedView || !sessionId}
                        onClick={endAndGetFeedback}
                        className="rounded-lg border border-[rgba(189,48,40,.25)] bg-transparent px-3.5 py-2 text-xs text-[rgba(189,48,40,.65)] transition hover:border-[rgba(189,48,40,.5)] hover:text-[#bd3028] disabled:opacity-40"
                      >
                        End & feedback
                      </button>
                    </div>
                  </div>

                  <div className="flex min-h-0 flex-col overflow-hidden rounded-[20px] border border-[rgba(73,38,31,.14)] bg-[#fffaf5] shadow-[0_18px_50px_rgba(73,38,31,.08)]">
                    <div className="flex shrink-0 items-center justify-between border-b border-[rgba(73,38,31,.14)] px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full bg-[#ff6b6b]" />
                        <span className="h-2.5 w-2.5 rounded-full bg-[#ffd93d]" />
                        <span className="h-2.5 w-2.5 rounded-full bg-[#6bcb77]" />
                        <span className="w-2" />
                        {languages.map((lang) => (
                          <button
                            key={lang.id}
                            onClick={() => setCurrentLang(lang.id)}
                            className={`rounded-md border px-2.5 py-1 text-[.72rem] font-medium font-mono transition ${currentLang === lang.id
                              ? "border-[rgba(189,48,40,.3)] bg-[rgba(189,48,40,.06)] text-[#bd3028]"
                              : "border-[rgba(73,38,31,.14)] bg-[#f4efe9] text-[#67534d]"
                              }`}
                          >
                            {lang.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <textarea
                      disabled={isSavedView}
                      spellCheck={false}
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Tab") {
                          e.preventDefault();
                          const target = e.currentTarget;
                          const start = target.selectionStart;
                          const end = target.selectionEnd;
                          target.setRangeText("  ", start, end, "end");
                          setCode(target.value);
                        }
                      }}
                      className="min-h-0 flex-1 resize-none overflow-auto bg-[#2c211e] p-[18px_20px] font-mono text-[.82rem] leading-[1.7] text-[#f4d7b9] outline-none disabled:opacity-60"
                      placeholder="# Write your solution here..."
                    />

                    <div className="flex shrink-0 items-center justify-between border-t border-[rgba(73,38,31,.14)] px-4 py-3">
                      <span className="text-[.72rem] text-[#977c73]">
                        Tab = 2 spaces · Share with interviewer when ready
                      </span>
                      <button
                        disabled={isSavedView}
                        onClick={submitCode}
                        className="flex items-center gap-1.5 rounded-lg border border-[rgba(46,118,88,.28)] bg-[rgba(46,118,88,.08)] px-4 py-2 text-xs font-medium text-[#2e7658] hover:bg-[rgba(46,118,88,.14)] disabled:opacity-40"
                      >
                        ↑ Submit to Interviewer
                      </button>
                    </div>
                  </div>
                </div>
              </section>
            )}
          </main>

          {showFeedback && (
            <div
              className="fixed inset-0 z-200 flex items-center justify-center overflow-y-auto bg-[rgba(44,33,30,.48)] p-5"
              role="dialog"
              aria-modal="true"
            >
              <div className="max-h-[90vh] w-full max-w-190 overflow-y-auto rounded-[18px] bg-[#fffaf5] p-6 text-[#2c211e] shadow-[0_24px_80px_rgba(44,33,30,.28)] sm:p-[30px]">
                <div className="mb-5.5 flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <button
                      onClick={() => setShowFeedback(false)}
                      className="h-8 w-8 rounded-lg border border-[rgba(73,38,31,.14)] bg-transparent text-xl leading-none text-[#67534d] hover:border-[rgba(189,48,40,.45)] hover:text-[#bd3028]"
                      aria-label="Close feedback"
                    >
                      ×
                    </button>
                    <div>
                      <div className="mb-2 text-[.7rem] font-semibold uppercase tracking-[.12em] text-[#977c73]">
                        Interview review
                      </div>
                      <h2 className="text-[1.45rem] font-semibold">Your feedback</h2>
                    </div>
                  </div>
                  <div className="text-3xl font-semibold text-[#bd3028]">
                    {feedback?.overall_score != null ? `${feedback.overall_score}/100` : "—"}
                  </div>
                </div>

                <div className="mb-5 leading-[1.6] text-[#67534d]">
                  {feedback?.summary || feedback?.error || "No feedback was available."}
                </div>

                <FeedbackSection
                  title="What worked"
                  items={(feedback?.strong_points || []).map((x) =>
                    `${x.title || ""}${x.detail ? ` — ${x.detail}` : ""}`
                  )}
                />
                <FeedbackSection
                  title="Where to improve"
                  items={
                    (feedback?.pain_points || []).length
                      ? (feedback?.pain_points || []).map((x) =>
                        `${x.title || ""}${x.detail ? ` — ${x.detail}` : ""}`
                      )
                      : (feedback?.areas_of_improvement || []).map((x) =>
                        `${x.title || ""}${x.action ? ` — ${x.action}` : ""}`
                      )
                  }
                />
                <FeedbackSection title="Next practice steps" items={feedback?.next_steps || []} />

                <div className="mt-6 flex justify-end">
                  <button
                    onClick={resetInterview}
                    className="rounded-[9px] bg-[#bd3028] px-4 py-2.5 text-sm text-white"
                  >
                    Start another interview
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Show>
      <Show when="signed-out">
        <div className="relative flex min-h-screen w-screen items-center justify-center overflow-hidden bg-[#f4efe9] px-5 py-10 text-[#2c211e]">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-[#bd3028]" />
          <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full border-[36px] border-[rgba(189,48,40,.08)]" />
          <div className="pointer-events-none absolute -bottom-32 -right-20 h-80 w-80 rounded-full border-[48px] border-[rgba(46,118,88,.08)]" />
          <div className="relative w-full max-w-105 rounded-[24px] border border-[rgba(73,38,31,.14)] bg-[#fffaf5] p-8 shadow-[0_24px_70px_rgba(73,38,31,.12)] sm:p-10">
            <div className="mb-10 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#bd3028] text-lg font-bold text-[#fffaf5] shadow-[0_8px_20px_rgba(189,48,40,.22)]">NF</div>
              <div>
                <div className="text-base font-semibold tracking-tight">NoFoxAI</div>
                <div className="text-xs text-[#977c73]">No fox given. Just practice.</div>
              </div>
            </div>
            <div className="mb-8">
              <div className="mb-3 text-[.7rem] font-semibold uppercase tracking-[.14em] text-[#bd3028]">Your interview room</div>
              <h1 className="text-[2.35rem] font-light leading-[1.08] tracking-[-.04em]">Practice with<br /><strong className="font-semibold">real confidence.</strong></h1>
              <p className="mt-4 max-w-85 text-sm leading-6 text-[#67534d]">Sign in to run voice interviews, save your conversations, and return to feedback whenever you need it.</p>
            </div>
            <SignInButton mode="modal">
              <button className="flex w-full items-center justify-center gap-3 rounded-xl bg-[#bd3028] px-4 py-3.5 text-sm font-semibold text-white shadow-[0_10px_24px_rgba(141,32,29,.18)] transition hover:-translate-y-px hover:bg-[#a92822] hover:shadow-[0_14px_30px_rgba(141,32,29,.24)]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white text-xs font-bold text-[#bd3028]">G</span>
                Continue with Google
              </button>
            </SignInButton>
            <p className="mt-5 text-center text-xs leading-5 text-[#977c73]">Your saved interviews are private to your account.</p>
          </div>
        </div>
      </Show>
    </>
  );
}

function FeedbackSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="mt-4.5">
      <h3 className="mb-2 text-[.72rem] font-semibold uppercase tracking-widest text-[#bd3028]">
        {title}
      </h3>
      <div className="grid gap-2 pl-4.5 text-sm leading-normal text-[#67534d]">
        {items.length ? (
          items.map((item, index) => (
            <div key={index}>
              <strong className="text-[#2c211e]">{item.split(" — ")[0]}</strong>
              {item.includes(" — ") ? ` — ${item.split(" — ").slice(1).join(" — ")}` : ""}
            </div>
          ))
        ) : (
          <div className="text-[#977c73]">No data available.</div>
        )}
      </div>
    </section>
  );
}