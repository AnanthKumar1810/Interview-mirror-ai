/* Interview content: tracks, languages, question bank and sample sessions. */
import type { Domain, Language, Question, Session } from "./types";

export const DOMAINS: Domain[] = [
  {
    id: "backend_eng",
    name: "Backend Engineering",
    badge: "FastAPI • AsyncIO • SQLite/Postgres",
    description:
      "Event-loop concurrency, REST & WebSocket API contracts, database indexing, transaction isolation, and distributed caching.",
    competencies: [
      "Python Fundamentals",
      "Backend Development",
      "API Design",
      "Concurrency",
      "System Design",
    ],
  },
  {
    id: "software_eng",
    name: "Software Engineering",
    badge: "DSA • Modularity • Testing",
    description:
      "Data structures, algorithmic trade-offs, object-oriented & functional design, debugging methodology, and production reliability.",
    competencies: ["Python Fundamentals", "API Design", "System Design", "Code Quality & Testing"],
  },
  {
    id: "ai_ml",
    name: "AI / Machine Learning",
    badge: "PyTorch • Evaluation • Deployment",
    description:
      "Model architectures, bias-variance trade-offs, latency-aware inference serving, evaluation metrics, and feature pipelines.",
    competencies: [
      "Python Fundamentals",
      "ML Modeling & Evaluation",
      "Inference Optimization",
      "Data Pipelines",
    ],
  },
  {
    id: "agentic_ai",
    name: "Agentic AI",
    badge: "Tool Use • State Machines • RAG",
    description:
      "Deterministic state machines, tool-call validation, context window management, retrieval grounding, and hallucination guardrails.",
    competencies: ["Agent State Machines", "RAG & Grounding", "API Design", "Concurrency"],
  },
  {
    id: "data_eng",
    name: "Data Engineering",
    badge: "ETL • Streaming • Warehousing",
    description:
      "Batch and streaming ingestion, schema evolution, partitioning strategies, idempotency, and SQL query optimization.",
    competencies: [
      "Data Pipelines",
      "SQL & Storage Internals",
      "System Design",
      "Python Fundamentals",
    ],
  },
].filter((domain) => ["software_eng", "ai_ml", "agentic_ai"].includes(domain.id));

export const LANGUAGES: Language[] = [
  {
    code: "en-IN",
    label: "English",
    native: "English (India)",
    guidance: "Clear technical English, tuned for Indian English accents.",
  },
  {
    code: "te-IN",
    label: "Telugu",
    native: "తెలుగు (Telugu + English Code-Mix)",
    guidance:
      "Explain concepts naturally in Telugu while retaining English technical terms (e.g., asyncio, FastAPI, deadlock, index).",
  },
  {
    code: "hi-IN",
    label: "Hindi",
    native: "हिन्दी (Hindi + English Code-Mix)",
    guidance:
      "Converse naturally in Hindi or Hinglish while keeping code identifiers, architecture patterns, and API terms in English.",
  },
];

const backend_eng: Question[] = [
  {
    id: "be_q1",
    topic: "Concurrency & Event Loop",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        "How does Python’s asyncio event loop handle a synchronous blocking I/O call inside an async def FastAPI endpoint, and how do you prevent it from stalling concurrent WebSocket streams?",
      "te-IN":
        "FastAPI లోని async def endpoint లోపల synchronous blocking I/O call రన్ అయితే Python asyncio event loop ఎలా స్పందిస్తుంది? ఇతర WebSocket కనెక్షన్లు ఆగిపోకుండా (stall అవ్వకుండా) మీరు ఎలా నివారించగలరు?",
      "hi-IN":
        "FastAPI के async def endpoint के अंदर अगर कोई synchronous blocking I/O call चलता है, तो Python का asyncio event loop उसे कैसे संभालता है? आप अन्य WebSocket स्ट्रीम्स को ब्लॉक होने से कैसे बचाएंगे?",
    },
    expectedConcepts: [
      "Single-threaded event loop blocking",
      "run_in_executor / anyio.to_thread",
      "def vs async def threadpool routing in FastAPI",
      "Non-blocking async drivers (aiosqlite / asyncpg)",
    ],
    sampleAnswers: {
      "en-IN":
        "Because the asyncio event loop runs on a single OS thread, calling synchronous blocking I/O like time.sleep or requests.get inside an async def route blocks the entire loop and stalls active WebSocket audio frames. To fix this, we either replace the call with an async driver like httpx.AsyncClient and aiosqlite, or offload CPU/blocking work using anyio.to_thread.run_sync or loop.run_in_executor.",
      "te-IN":
        "Asyncio event loop సింగిల్ థ్రెడ్ మీద పనిచేస్తుంది కాబట్టి, async def endpoint లోపల blocking I/O కాల్ చేస్తే మొత్తం event loop బ్లాక్ అయిపోతుంది మరియు WebSocket ఆడియో ఫ్రేమ్స్ ఆలస్యం అవుతాయి. దీన్ని నివారించడానికి httpx లేదా aiosqlite వంటి non-blocking async లైబ्रेరీలను వాడాలి, లేదా blocking కోడ్‌ను run_in_executor / threadpool ద్వారా రన్ చేయాలి.",
      "hi-IN":
        "चूँकि asyncio event loop एक सिंगल थ्रेड पर चलता है, इसलिए async def के अंदर synchronous blocking I/O कॉल करने से पूरा event loop रुक जाता है और WebSocket स्ट्रीम्स में देरी होती है। इसे रोकने के लिए हमें aiosqlite या httpx जैसे async ड्राइवर का उपयोग करना चाहिए, या किसी थ्रेडपूल में run_in_executor का उपयोग करना चाहिए।",
    },
  },
  {
    id: "be_q2",
    topic: "Database Persistence & SQLite Concurrency",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        "In InterviewMirror’s SQLite session store, how does enabling Write-Ahead Logging (WAL) improve concurrent read/write behavior during real-time transcript persistence?",
      "te-IN":
        "రియల్-టైమ్ ట్రాన్స్‌క్రిప్ట్ సేవ్ చేసేటప్పుడు SQLite డేటాబేస్‌లో Write-Ahead Logging (WAL) మోడ్ ఎనేబుల్ చేయడం వల్ల రీడ్ మరియు రైట్ concurrency ఎలా మెరుగుపడుతుంది?",
      "hi-IN":
        "रियल-टाइम ट्रांसक्रिप्ट सेव करते समय SQLite में Write-Ahead Logging (WAL) मोड ऑन करने से रीड और राइट concurrency कैसे बेहतर होती है?",
    },
    expectedConcepts: [
      "Readers do not block writers",
      "Sequential append to -wal file",
      "Checkpointing back to main DB file",
      "busy_timeout configuration",
    ],
    sampleAnswers: {
      "en-IN":
        "In default rollback journal mode, a write locks the entire SQLite database file, blocking readers. With PRAGMA journal_mode=WAL, changes are appended sequentially to a separate WAL file, allowing concurrent readers to read consistent snapshots while a single writer appends transcript segments, paired with a busy_timeout to handle brief write contention.",
      "te-IN":
        "సాధారణ జర్నల్ మోడ్‌లో రైట్ ఆపరేషన్ జరుగుతున్నప్పుడు రీడర్స్ బ్లాక్ అవుతాయి. కానీ PRAGMA journal_mode=WAL వాడినప్పుడు కొత్త ట్రాన్స్‌క్రిప్ట్ డేటా వేరే WAL ఫైల్‌లోకి సీక్వెన్షియల్‌గా వ్రాయబడుతుంది, దీనివల్ల రీడర్స్ మరియు రైటర్ ఒకేసారి బ్లాక్ అవ్వకుండా పనిచేస్తాయి.",
      "hi-IN":
        "डिफ़ॉल्ट मोड में राइट करते समय पूरी डेटाबेस फ़ाइल लॉक हो जाती है। PRAGMA journal_mode=WAL के साथ नए बदलाव एक अलग WAL फ़ाइल में जुड़ते जाते हैं, जिससे रीडर्स को ब्लॉक किए बिना ट्रांसक्रिप्ट सेगमेंट सेव किए जा सकते हैं।",
    },
  },
  {
    id: "be_q3",
    topic: "WebSocket Streaming & Backpressure",
    difficulty: "Advanced",
    prompt: {
      "en-IN":
        "When streaming 16kHz PCM16 audio frames from the browser AudioWorklet to FastAPI and Gnani Prisma, how do you design bounded buffering and barge-in cancellation?",
      "te-IN":
        "బ్రౌజర్ AudioWorklet నుండి FastAPI మరియు Gnani Prisma కి 16kHz PCM16 ఆడియో ఫ్రేమ్స్ స్ట్రీమ్ చేస్తున్నప్పుడు, backpressure మరియు barge-in క్యాన్సిలేషన్ ఎలా డిజైన్ చేస్తారు?",
      "hi-IN":
        "ब्राउज़र AudioWorklet से FastAPI और Gnani Prisma तक 16kHz PCM16 ऑडियो स्ट्रीम करते समय आप बाउंडेड बफरिंग और बार्ज-इन (barge-in) कैंसिलेशन कैसे डिज़ाइन करेंगे?",
    },
    expectedConcepts: [
      "Bounded asyncio.Queue capacity",
      "Dropping or coalescing stale TTS buffers on barge-in",
      "Sequence/turn IDs to ignore stale audio",
      "Graceful WebSocket reconnect state",
    ],
    sampleAnswers: {
      "en-IN":
        "We use a bounded asyncio.Queue between the FastAPI WebSocket receiver and the Gnani Prisma gRPC stream so slow downstream network hops do not cause unbounded memory growth. For barge-in, each interviewer turn carries a monotonic turn_id; when speech activity is confirmed, the client flushes its WebAudio playback queue and sends a barge_in event so the server cancels in-flight Timbre TTS synthesis for that turn_id.",
      "te-IN":
        "మెమరీ పెరిగిపోకుండా ఉండటానికి మేము FastAPI WebSocket మరియు Gnani Prisma మధ్య bounded asyncio.Queue వాడతాము. అభ్యర్థి మధ్యలో మాట్లాడినప్పుడు (barge-in), ప్రతి సమాధానానికి ఉండే turn_id ఆధారంగా పాత Timbre TTS ఆడియో బఫర్‌లను వెంటనే ఆపివేసి Listening స్టేట్‌కి మారుస్తాము.",
      "hi-IN":
        "मेमोरी को सुरक्षित रखने के लिए हम FastAPI WebSocket और Gnani Prisma के बीच bounded asyncio.Queue का उपयोग करते हैं। जब उम्मीदवार बीच में बोलता है (barge-in), तो हम turn_id की मदद से पुराने Timbre TTS ऑडियो बफ़र को तुरंत रद्द कर देते हैं।",
    },
  },
  {
    id: "be_q4",
    topic: "API Idempotency & Error Recovery",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        'If a candidate clicks "End Interview" twice during a high-latency network spike, how do you ensure the backend generates exactly one performance report without duplicate scoring runs?',
      "te-IN":
        'నెట్‌వర్క్ ఆలస్యంగా ఉన్నప్పుడు అభ్యర్థి "End Interview" బటన్‌ను రెండుసార్లు క్లిక్ చేస్తే, డూప్లికేట్ రిపోర్టులు తయారవ్వకుండా బ్యాకెండ్‌లో idempotency ఎలా అమలు చేస్తారు?',
      "hi-IN":
        'यदि नेटवर्क धीमा होने पर उम्मीदवार दो बार "End Interview" दबाता है, तो आप यह कैसे सुनिश्चित करेंगे कि बैकएंड बिना डुप्लिकेट स्कोरिंग के केवल एक ही रिपोर्ट बनाए?',
    },
    expectedConcepts: [
      "Idempotency key / atomic state transition",
      "Database unique constraint on session report",
      "Frontend button lock during termination",
      "Returning cached report on retry",
    ],
    sampleAnswers: {
      "en-IN":
        "On the frontend, we immediately lock the End Interview control and transition to a finalizing state. On the backend, the session state machine performs an atomic compare-and-swap transition from ACTIVE to FINALIZING in SQLite and enforces a unique session_id constraint on the reports table so duplicate requests simply await and return the single generated report.",
      "te-IN":
        "ఫ్రంట్‌ఎండ్‌లో వెంటనే బటన్‌ను డిసేబుల్ చేసి ఫైనలైజింగ్ స్టేట్ చూపిస్తాము. బ్యాకెండ్‌లో SQLite లో session_id పై unique constraint పెట్టి, ACTIVE నుండి COMPLETED కి అటామిక్ స్టేట్ ట్రాన్సిషన్ చేయడం ద్వారా ఒకే రిపోర్ట్ జనరేట్ అయ్యేలా చూస్తాము.",
      "hi-IN":
        "फ्रंटएंड पर हम तुरंत बटन को लॉक कर देते हैं। बैकएंड पर SQLite में session_id पर unique constraint और atomic state transition का उपयोग किया जाता है ताकि दोबारा अनुरोध आने पर वही एक रिपोर्ट वापस मिले।",
    },
  },
  {
    id: "be_q5",
    topic: "Authentication & Session Security",
    difficulty: "Fundamentals",
    prompt: {
      "en-IN":
        "Why should Gnani API credentials and raw provider tokens never be exposed to the browser client, and how should WebSocket session authentication be validated?",
      "te-IN":
        "Gnani API keys మరియు ప్రొవైడర్ టోకెన్లను బ్రౌజర్ క్లయింట్‌లో ఎందుకు ఉంచకూడదు? మరియు WebSocket సెషన్ ఆథెంటికేషన్‌ను ఎలా ధృవీకరించాలి?",
      "hi-IN":
        "Gnani API कुंजियों (keys) को कभी भी ब्राउज़र क्लाइंट में क्यों नहीं रखना चाहिए, और WebSocket सेशन प्रमाणीकरण (authentication) की जाँच कैसे की जानी चाहिए?",
    },
    expectedConcepts: [
      "Server-side secret isolation",
      "Short-lived session-scoped token or HttpOnly cookie",
      "Per-session ownership authorization check",
      "Preventing cross-account report leakage",
    ],
    sampleAnswers: {
      "en-IN":
        "Exposing provider keys in client code allows anyone to extract them from DevTools and abuse billing quotas. Instead, the browser authenticates with FastAPI using a short-lived session token or HttpOnly session cookie, FastAPI validates that the authenticated user owns the requested session_id before upgrading the WebSocket, and all Gnani gRPC calls happen strictly server-to-server.",
      "te-IN":
        "క్లయింట్ కోడ్‌లో API keys పెడితే ఎవరైనా DevTools ద్వారా వాటిని తీసుకుని దుర్వినియోగం చేయవచ్చు. అందుకే బ్రౌజర్ కేవలం FastAPI సెషన్ టోకెన్‌తో మాత్రమే కనెక్ట్ అవ్వాలి మరియు FastAPI ఆ సెషన్ ఆ యూజర్‌దేనా అని తనిఖీ చేసిన తర్వాతే సర్వర్ నుండి Gnani కి కనెక్ట్ చేయాలి.",
      "hi-IN":
        "ब्राउज़र में API keys रखने से कोई भी उन्हें DevTools से चुरा सकता है। इसलिए ब्राउज़र केवल अल्पकालिक सेशन टोकन के साथ FastAPI से जुड़ता है, और FastAPI उपयोगकर्ता के अधिकार की जाँच करने के बाद सर्वर से Gnani को कॉल करता है।",
    },
  },
  {
    id: "be_q6",
    topic: "Resume & GitHub Personalization Grounding",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        "When adapting interview follow-up questions to a candidate’s uploaded resume or GitHub repository, how do you verify deep project understanding rather than surface buzzwords?",
      "te-IN":
        "అభ్యర్థి రెస్యూమ్ లేదా GitHub ప్రాజెక్ట్ ఆధారంగా ప్రశ్నలు అడిగేటప్పుడు, కేవలం పదాలు కాకుండా నిజమైన ప్రాజెక్ట్ అవగాహనను ఎలా పరీక్షిస్తారు?",
      "hi-IN":
        "उम्मीदवार के रेज़्यूमे या GitHub प्रोजेक्ट के आधार पर प्रश्न पूछते समय आप सतही शब्दों के बजाय गहरी समझ की जाँच कैसे करते हैं?",
    },
    expectedConcepts: [
      "Probing architectural trade-offs",
      "Asking about failure modes and bottlenecks",
      "Verifying specific metric claims",
      "Contextual follow-up based on candidate response",
    ],
    sampleAnswers: {
      "en-IN":
        "Instead of asking generic definitions, the state machine extracts concrete architectural claims from the candidate profile and probes specific trade-offs—such as why a particular queue or index was chosen, what failed under load, and how latency or accuracy was measured.",
      "te-IN":
        "సాధారణ నిర్వచనాలు అడగకుండా, అభ్యర్థి ప్రాజెక్ట్‌లో తీసుకున్న డిజైన్ నిర్ణయాలు, ఎదురైన సమస్యలు మరియు వాటిని ఎలా పరిష్కరించారో లోతైన ఫాలో-అప్ ప్రశ్నల ద్వారా పరీక్షిస్తాము.",
      "hi-IN":
        "सामान्य परिभाषाएँ पूछने के बजाय, हम प्रोजेक्ट में लिए गए आर्किटेक्चरल निर्णयों, विफलताओं (failure modes) और प्रदर्शन मापदंडों पर आधारित फॉलो-अप प्रश्न पूछते हैं।",
    },
  },
  {
    id: "be_q7",
    topic: "Observability & Tail Latency",
    difficulty: "Advanced",
    prompt: {
      "en-IN":
        "How would you instrument end-to-end turn latency across AudioWorklet capture, Prisma ASR finals, LLM follow-up generation, and Timbre TTS first-byte playback?",
      "te-IN":
        "AudioWorklet క్యాప్చర్ నుండి Prisma ASR, ఫాలో-అప్ ప్రశ్న జనరేషన్ మరియు Timbre TTS ప్లేబ్యాక్ వరకు ఎండ్-టు-ఎండ్ latency ని ఎలా కొలుస్తారు?",
      "hi-IN":
        "AudioWorklet कैप्चर से लेकर Prisma ASR, फॉलो-अप जनरेशन और Timbre TTS प्लेबैक तक आप एंड-टू-एंड लेटेंसी (latency) को कैसे मापेंगे?",
    },
    expectedConcepts: [
      "Stage-by-stage monotonic timestamps",
      "P50/P95/P99 latency breakdown",
      "Time-to-First-Audio-Byte (TTFAB)",
      "Correlation via session_id and turn_id",
    ],
    sampleAnswers: {
      "en-IN":
        "We attach monotonic stage timestamps keyed by session_id and turn_id: speech_end_detected_at, asr_final_received_at, llm_prompt_ready_at, tts_first_chunk_at, and client_playback_started_at. Tracking P50 and P95 across each stage isolates whether latency spikes come from network jitter, ASR finalization, or TTS synthesis.",
      "te-IN":
        "ప్రతి turn_id కి monotonic timestamps జోడించి ASR ఫైనల్ సమయం, LLM ప్రాసెసింగ్ సమయం మరియు TTS మొదటి ఆడియో బైట్ సమయాన్ని విడివిడిగా P50/P95 మెట్రిక్స్‌తో ట్రాక్ చేస్తాము.",
      "hi-IN":
        "हम प्रत्येक turn_id के लिए अलग-अलग स्टेज के टाइमस्टैम्प रिकॉर्ड करते हैं ताकि P50 और P95 लेटेंसी से पता चल सके कि देरी नेटवर्क, ASR या TTS किस स्तर पर हो रही है।",
    },
  },
];

// Populate other domains by extending with domain-specific questions + core questions
const software_eng: Question[] = [
  {
    id: "se_q1",
    topic: "API Contracts & State Consistency",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        "How do you prevent race conditions between concurrent frontend state transitions and asynchronous backend WebSocket events in a real-time application?",
      "te-IN":
        "రియల్-టైమ్ అప్లికేషన్‌లో ఫ్రంట్‌ఎండ్ స్టేట్ మరియు బ్యాకెండ్ WebSocket ఈవెంట్స్ మధ్య race conditions రాకుండా ఎలా నివారిస్తారు?",
      "hi-IN":
        "एक रियल-टाइम एप्लिकेशन में फ्रंटएंड स्टेट और बैकएंड WebSocket इवेंट्स के बीच रेस कंडीशन (race conditions) को कैसे रोका जाता है?",
    },
    expectedConcepts: [
      "Single authoritative state machine",
      "Monotonic sequence numbers / turn IDs",
      "Ignoring stale async responses",
      "Deterministic cleanup on unmount",
    ],
    sampleAnswers: {
      "en-IN":
        "We maintain a single authoritative state store where every state transition carries a monotonic sequence number and turn_id. If a late WebSocket event arrives for an older turn_id after a barge-in or session termination, the reducer deterministically discards it.",
      "te-IN":
        "ఒకే అధికారిక స్టేట్ మెషీన్‌ను ఉంచి ప్రతి ఈవెంట్‌కు turn_id మరియు సీక్వెన్స్ నంబర్ ఇస్తాము. పాత turn_id నుండి ఆలస్యంగా వచ్చే ఈవెంట్లను విస్మరించడం ద్వారా race conditions నివారిస్తాము.",
      "hi-IN":
        "हम एक सिंगल स्टेट मशीन रखते हैं जिसमें हर इवेंट के साथ turn_id और सीक्वेंस नंबर होता है, ताकि पुराने टर्न से आने वाले लेट इवेंट्स को सुरक्षित रूप से अनदेखा किया जा सके।",
    },
  },
  ...backend_eng.slice(0, 6),
];

const ai_ml: Question[] = [
  {
    id: "ai_q1",
    topic: "Speech Recognition & Code-Mixed ASR",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        "What acoustic and language-modeling challenges arise when transcribing code-mixed Telugu-English or Hindi-English technical interviews, and how should post-ASR correction preserve technical identifiers?",
      "te-IN":
        "తెలుగు-ఇంగ్లీష్ (code-mixed) టెక్నికల్ ఇంటర్వ్యూలను ట్రాన్స్‌క్రైబ్ చేసేటప్పుడు ఎలాంటి సవాళ్లు ఎదురవుతాయి? టెక్నికల్ పదాలను తప్పుగా మార్చకుండా ఎలా కాపాడాలి?",
      "hi-IN":
        "हिंदी-अंग्रेज़ी (code-mixed) तकनीकी साक्षात्कारों को ट्रांसक्राइब करते समय क्या चुनौतियाँ आती हैं, और तकनीकी शब्दों को सुरक्षित कैसे रखा जाता है?",
    },
    expectedConcepts: [
      "Phonetic transliteration ambiguity",
      "Domain vocabulary biasing (FastAPI, asyncio, SQLite)",
      "Confidence-gated post-correction",
      "Preserving candidate intent without fabricating concepts",
    ],
    sampleAnswers: {
      "en-IN":
        "Code-mixed speech switches rapidly between Indic morphology and English technical terms like asyncio or idempotency, which general ASR models often split into phonetic native-script approximations. We apply domain-lexicon biasing and confidence-gated normalization that maps phonetic technical tokens back to canonical identifiers without altering the candidate’s underlying explanation.",
      "te-IN":
        "తెలుగులో మాట్లాడుతున్నప్పుడు మధ్యలో వచ్చే asyncio లేదా FastAPI వంటి ఇంగ్లీష్ పదాలను సాధారణ ASR మోడల్స్ తప్పుగా గుర్తించవచ్చు. అందుకే డొమైన్ పదకోశం (lexicon biasing) మరియు confidence-gated కరెక్షన్ వాడి అభ్యర్థి భావాన్ని మార్చకుండా టెక్నికల్ పదాలను సరిచేస్తాము.",
      "hi-IN":
        "कोड-मिक्स्ड भाषण में तकनीकी शब्दों का उच्चारण अक्सर सामान्य ASR को भ्रमित करता है। हम डोमेन शब्दावली बायसिंग और कॉन्फिडेंस-गेटेड सुधार का उपयोग करते हैं ताकि उम्मीदवार के मूल उत्तर को बदले बिना तकनीकी शब्दों को सही रूप में लिखा जा सके।",
    },
  },
  ...backend_eng.slice(0, 6),
];

const agentic_ai: Question[] = [
  {
    id: "ag_q1",
    topic: "Adaptive Interview State Machine & Guardrails",
    difficulty: "Advanced",
    prompt: {
      "en-IN":
        "Why does InterviewMirror use an explicit finite state machine paired with evidence-linked rubric evaluation instead of an unconstrained free-form chatbot prompt?",
      "te-IN":
        "సాధారణ చాట్‌బాట్ లాగా కాకుండా InterviewMirror లో స్పష్టమైన finite state machine మరియు ఆధారాలతో కూడిన (evidence-linked) మూల్యాంకనం ఎందుకు వాడుతున్నారు?",
      "hi-IN":
        "सामान्य चैटबॉट प्रॉम्प्ट के बजाय InterviewMirror में स्पष्ट फाइनाइट स्टेट मशीन (finite state machine) और साक्ष्य-आधारित मूल्यांकन का उपयोग क्यों किया जाता है?",
    },
    expectedConcepts: [
      "Deterministic turn progression",
      "Preventing hallucinated praise or uncalibrated scores",
      "Evidence quotes tied to transcript segments",
      "Controlled follow-up depth limits",
    ],
    sampleAnswers: {
      "en-IN":
        "An unconstrained chatbot can drift off-topic, hallucinate generic praise, or get stuck in infinite follow-up loops. An explicit state machine enforces turn budgets, transitions cleanly between primary questions and targeted probes based on missing concept coverage, and requires every rubric score to link directly to verbatim transcript evidence.",
      "te-IN":
        "సాధారణ చాట్‌బాట్ అంశం నుండి పక్కకు వెళ్ళవచ్చు లేదా ఆధారాలు లేకుండా మార్కులు ఇవ్వవచ్చు. అదే finite state machine అయితే ప్రశ్నల సంఖ్యను నియంత్రిస్తుంది మరియు అభ్యర్థి సమాధానంలోని ఖచ్చితమైన వాక్యాల ఆధారంగా మాత్రమే ఫీడ్‌బ్యాక్ ఇస్తుంది.",
      "hi-IN":
        "एक अनियंत्रित चैटबॉट विषय से भटक सकता है या बिना प्रमाण के प्रशंसा कर सकता है। एक स्पष्ट स्टेट मशीन प्रश्नों की सीमा तय करती है और प्रत्येक स्कोर को उम्मीदवार के वास्तविक उत्तर के साक्ष्य से जोड़ती है।",
    },
  },
  ...backend_eng.slice(0, 6),
];

const data_eng: Question[] = [
  {
    id: "de_q1",
    topic: "Streaming Telemetry & Schema Evolution",
    difficulty: "Intermediate",
    prompt: {
      "en-IN":
        "How do you design an idempotent event schema for storing real-time interview transcript segments, competency evidence, and latency telemetry across schema versions?",
      "te-IN":
        "రియల్-టైమ్ ట్రాన్స్‌క్రిప్ట్ సెగ్మెంట్లు మరియు టెలిమెట్రీ డేటాను భద్రపరచడానికి idempotent ఈవెంట్ స్కీమాను ఎలా డిజైన్ చేస్తారు?",
      "hi-IN":
        "रियल-टाइम ट्रांसक्रिप्ट सेगमेंट और टेलीमेट्री डेटा को स्टोर करने के लिए आप एक idempotent इवेंट स्कीमा कैसे डिज़ाइन करेंगे?",
    },
    expectedConcepts: [
      "Composite primary key (session_id, turn_id, segment_seq)",
      "Additive backward-compatible migrations",
      "Immutable raw transcript + versioned correction layer",
      "Indexed query patterns for history & analytics",
    ],
    sampleAnswers: {
      "en-IN":
        "We key each transcript segment by a composite identifier (session_id, turn_id, segment_seq) so network retries upsert cleanly without duplication. Raw ASR output is stored immutably alongside an optional corrected_text column and schema_version tag so historical sessions remain queryable across migrations.",
      "te-IN":
        "ప్రతి ట్రాన్స్‌క్రిప్ట్ సెగ్మెంట్‌కు (session_id, turn_id, segment_seq) అనే కాంపోజిట్ కీ ఇవ్వడం వల్ల నెట్‌వర్క్ రీట్రై జరిగినా డూప్లికేట్ డేటా చేరదు. అసలు ట్రాన్స్‌క్రిప్ట్‌తో పాటు సవరించిన టెక్స్ట్‌ను వేరుగా సేవ్ చేస్తాము.",
      "hi-IN":
        "हम प्रत्येक सेगमेंट के लिए (session_id, turn_id, segment_seq) कम्पोज़िट कुंजी का उपयोग करते हैं ताकि दोबारा भेजने पर डुप्लिकेट डेटा न बने, और मूल ट्रांसक्रिप्ट के साथ संशोधित टेक्स्ट को सुरक्षित रखते हैं।",
    },
  },
  ...backend_eng.slice(0, 6),
];

export const BACKEND_QUESTIONS = backend_eng;
export const QUESTION_BANK: Record<string, Question[] | undefined> = {
  backend_eng,
  software_eng,
  ai_ml,
  agentic_ai,
  data_eng,
};

export function getDomain(id: string): Domain {
  return DOMAINS.find((d) => d.id === id) ?? (DOMAINS[0] as Domain);
}

export function getLanguage(code: string): Language {
  return LANGUAGES.find((l) => l.code === code) ?? (LANGUAGES[0] as Language);
}

// Sample sessions shown until the user records their own
export const SEEDED_SESSIONS: Session[] = [
  {
    id: "sess_2c8350e_01",
    domainId: "backend_eng",
    domainName: "Backend Engineering",
    targetRole: "Backend / Platform Engineer (FastAPI & Python)",
    languageCode: "te-IN",
    languageLabel: "Telugu (తెలుగు + English)",
    difficulty: "Intermediate",
    questionTarget: 3,
    questionsCompleted: 3,
    date: "2026-11-13 18:40 IST",
    durationSeconds: 495,
    durationFormatted: "08m 15s",
    status: "Completed",
    overallScore: 78,
    dimensions: {
      technicalAccuracy: 82,
      designTradeoffs: 76,
      projectUnderstanding: 80,
      communicationClarity: 74,
    },
    strengths: [
      "Clearly explained why synchronous blocking calls stall the single-threaded Python asyncio event loop during active WebSocket audio streaming.",
      "Accurately described SQLite Write-Ahead Logging (PRAGMA journal_mode=WAL) and why readers do not block concurrent transcript appends.",
      "Maintained natural code-mixed Telugu-English technical fluency while keeping API and concurrency terms exact.",
    ],
    improvements: [
      "Specify bounded queue sizing and turn_id cancellation mechanics when discussing WebSocket backpressure and barge-in handling.",
      "Quantify SQLite busy_timeout thresholds and checkpoint intervals under sustained write bursts.",
    ],
    roadmap: [
      {
        step: "Review bounded asyncio.Queue backpressure patterns",
        detail:
          "Practice implementing maxsize queues with explicit drop/cancel policies when downstream ASR streams lag.",
      },
      {
        step: "Trace barge-in turn_id invalidation end-to-end",
        detail:
          "Walk through how client WebAudio buffer flushing coordinates with server-side Timbre TTS cancellation.",
      },
      {
        step: "Benchmark SQLite WAL busy_timeout settings",
        detail:
          "Test concurrent read/write session persistence with PRAGMA busy_timeout = 5000 and WAL auto-checkpointing.",
      },
    ],
    turns: [
      {
        turnIndex: 1,
        topic: "Concurrency & Event Loop",
        question:
          "FastAPI లోని async def endpoint లోపల synchronous blocking I/O call రన్ అయితే Python asyncio event loop ఎలా స్పందిస్తుంది? ఇతర WebSocket కనెక్షన్లు ఆగిపోకుండా మీరు ఎలా నివారించగలరు?",
        rawTranscript:
          "Asyncio event loop సింగిల్ థ్రెడ్ మీద పనిచేస్తుంది కాబట్టి async def లోపల blocking call చేస్తే మొత్తం event loop బ్లాక్ అవుతుంది. దీన్ని ఆపడానికి aiosqlite లేదా httpx లాంటి async libraries వాడాలి లేదా run_in_executor వాడాలి.",
        correctedTranscript:
          "Asyncio event loop సింగిల్ థ్రెడ్ మీద పనిచేస్తుంది కాబట్టి async def లోపల blocking I/O call చేస్తే మొత్తం event loop బ్లాక్ అవుతుంది మరియు WebSocket ఫ్రేమ్స్ ఆలస్యం అవుతాయి. దీన్ని నివారించడానికి aiosqlite లేదా httpx లాంటి non-blocking async libraries వాడాలి, లేదా anyio.to_thread / run_in_executor వాడాలి.",
        score: 84,
        evidence:
          "Referenced single-threaded event loop blocking, async libraries (aiosqlite, httpx), and run_in_executor threadpool offloading.",
        missingConcepts: ["FastAPI def vs async def automatic threadpool routing distinction"],
        recommendation:
          "Explicitly contrast how FastAPI runs standard def endpoints in an external threadpool vs async def endpoints directly on the event loop.",
      },
      {
        turnIndex: 2,
        topic: "Database Persistence & SQLite Concurrency",
        question:
          "రియల్-టైమ్ ట్రాన్స్‌క్రిప్ట్ సేవ్ చేసేటప్పుడు SQLite డేటాబేస్‌లో Write-Ahead Logging (WAL) మోడ్ ఎనేబుల్ చేయడం వల్ల రీడ్ మరియు రైట్ concurrency ఎలా మెరుగుపడుతుంది?",
        rawTranscript:
          "PRAGMA journal_mode=WAL వాడినప్పుడు కొత్త డేటా WAL ఫైల్‌లోకి వెళ్తుంది, దీనివల్ల రీడర్స్ బ్లాక్ అవ్వకుండా ఒకేసారి పనిచేస్తాయి.",
        correctedTranscript:
          "PRAGMA journal_mode=WAL వాడినప్పుడు కొత్త ట్రాన్స్‌క్రిప్ట్ డేటా వేరే -wal ఫైల్‌లోకి సీక్వెన్షియల్‌గా వ్రాయబడుతుంది, దీనివల్ల రీడర్స్ బ్లాక్ అవ్వకుండా పనిచేస్తాయి.",
        score: 78,
        evidence: "Correctly identified PRAGMA journal_mode=WAL and non-blocking concurrent reads.",
        missingConcepts: ["Checkpointing back to main database file", "busy_timeout configuration"],
        recommendation:
          "Mention how WAL pages are periodically checkpointed back into the primary SQLite file and why PRAGMA busy_timeout prevents SQLITE_BUSY errors.",
      },
      {
        turnIndex: 3,
        topic: "WebSocket Streaming & Backpressure",
        question:
          "బ్రౌజర్ AudioWorklet నుండి FastAPI మరియు Gnani Prisma కి 16kHz PCM16 ఆడియో ఫ్రేమ్స్ స్ట్రీమ్ చేస్తున్నప్పుడు, backpressure మరియు barge-in క్యాన్సిలేషన్ ఎలా డిజైన్ చేస్తారు?",
        rawTranscript: "అభ్యర్థి మధ్యలో మాట్లాడినప్పుడు పాత ఆడియో ఆపేసి కొత్త ప్రశ్న వినేలా చేస్తాము మరియు క్యూ వాడతాము.",
        correctedTranscript:
          "అభ్యర్థి మధ్యలో మాట్లాడినప్పుడు (barge-in) పాత TTS ఆడియో బఫర్ ఆపేసి Listening స్టేట్‌కి మారుస్తాము మరియు మెమరీ కోసం asyncio.Queue వాడతాము.",
        score: 72,
        evidence: "Identified TTS playback cancellation on barge-in and queue usage.",
        missingConcepts: [
          "Bounded queue capacity (maxsize)",
          "Monotonic turn_id tagging to discard in-flight TTS chunks",
        ],
        recommendation:
          "Explain how a monotonic turn_id prevents late-arriving TTS audio chunks from playing after a barge-in interrupt.",
      },
    ],
  },
  {
    id: "sess_2c8350e_02",
    domainId: "agentic_ai",
    domainName: "Agentic AI",
    targetRole: "AI / ML & Agent Systems Engineer",
    languageCode: "en-IN",
    languageLabel: "English (India)",
    difficulty: "Advanced",
    questionTarget: 3,
    questionsCompleted: 3,
    date: "2026-11-10 20:15 IST",
    durationSeconds: 540,
    durationFormatted: "09m 00s",
    status: "Completed",
    overallScore: 81,
    dimensions: {
      technicalAccuracy: 85,
      designTradeoffs: 82,
      projectUnderstanding: 79,
      communicationClarity: 78,
    },
    strengths: [
      "Articulated deterministic state machine transitions vs unconstrained LLM prompting for technical interviews.",
      "Explained evidence-linked rubric grounding and why practice assessments must carry explicit calibration disclaimers.",
    ],
    improvements: [
      "Detail fallback recovery state transitions when upstream speech recognition streams time out mid-utterance.",
    ],
    roadmap: [
      {
        step: "Design timeout-safe ASR state transitions",
        detail:
          "Map exact recovery states when Prisma partial segments stall without a final acoustic marker.",
      },
      {
        step: "Refine rubric citation extraction",
        detail:
          "Ensure each competency score links to exact transcript turn indices and concept tags.",
      },
      {
        step: "Practice explaining latency budgets across ASR + LLM + TTS",
        detail: "Break down P95 turn-around budgets under 800ms.",
      },
    ],
    turns: [
      {
        turnIndex: 1,
        topic: "Adaptive Interview State Machine & Guardrails",
        question:
          "Why does InterviewMirror use an explicit finite state machine paired with evidence-linked rubric evaluation instead of an unconstrained free-form chatbot prompt?",
        rawTranscript:
          "An explicit state machine enforces turn budgets, transitions cleanly between primary questions and targeted probes based on missing concept coverage, and requires every rubric score to link directly to verbatim transcript evidence.",
        correctedTranscript:
          "An explicit state machine enforces turn budgets, transitions cleanly between primary questions and targeted probes based on missing concept coverage, and requires every rubric score to link directly to verbatim transcript evidence.",
        score: 88,
        evidence:
          "Directly addressed turn budgets, targeted follow-up transitions, and verbatim transcript evidence linking.",
        missingConcepts: [],
        recommendation:
          "Strong architectural answer; you can also note how deterministic states simplify UI voice orb synchronization.",
      },
    ],
  },
];

export const PRESETS: {
  key: string;
  label: string;
  emoji: string;
  setup: Partial<import("./types").SetupDraft>;
}[] = [
  {
    key: "fastapi_backend",
    label: "FastAPI backend",
    emoji: "⚡",
    setup: {
      domainId: "backend_eng",
      languageCode: "te-IN",
      difficulty: "Intermediate",
      questionTarget: 3,
      targetRole: "Senior Backend Engineer (FastAPI & Async Systems)",
      github: "github.com/candidate/async-voice-pipeline",
      highlights:
        "Built a FastAPI WebSocket streaming backend with SQLite WAL persistence and bounded asyncio.Queue backpressure.",
    },
  },
  {
    key: "agentic_ai",
    label: "Agentic AI",
    emoji: "🤖",
    setup: {
      domainId: "agentic_ai",
      languageCode: "en-IN",
      difficulty: "Advanced",
      questionTarget: 5,
      targetRole: "Agentic AI & Voice Systems Engineer",
      github: "github.com/candidate/deterministic-agent-fsm",
      highlights:
        "Built a finite-state-machine interview orchestrator with rubric evidence grounding and barge-in cancellation.",
    },
  },
  {
    key: "fullstack_hindi",
    label: "Full-stack APIs",
    emoji: "🛠",
    setup: {
      domainId: "software_eng",
      languageCode: "hi-IN",
      difficulty: "Intermediate",
      questionTarget: 3,
      targetRole: "Software Development Engineer (Full-Stack & APIs)",
      github: "github.com/candidate/distributed-task-runner",
      highlights:
        "Implemented idempotent REST APIs, monotonic state reducers and end-to-end contract tests.",
    },
  },
];
