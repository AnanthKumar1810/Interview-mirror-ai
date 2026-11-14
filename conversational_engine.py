"""Advanced Conversational Intelligence for InterviewMirror AI.

Implements:
1. CandidateKnowledgeModel: Structured tracking of demonstrated competencies,
   evidence, missing concepts, misconceptions, and confidence.
2. CompetencyGraph: Directed concept hierarchy per track guiding coherent,
   non-random follow-up exploration.
3. DialoguePolicy: Conversational intent handling (clarification, repeat,
   uncertainty, skip) without unfair grading penalties.
4. ContextualMemory: Auditable decision history for transparent interviewer actions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger("interviewmirror.conversational_engine")

# Conversational Intents
INTENT_CLARIFICATION = "clarification"
INTENT_REPEAT = "repeat"
INTENT_UNCERTAINTY = "uncertainty"
INTENT_SKIP = "skip"
INTENT_ANSWER = "answer"

# Intent Classification Patterns across English, Telugu, Hindi, and Code-Mix
CLARIFICATION_PATTERNS = [
    re.compile(r"\b(?:what\s+do\s+you\s+mean|could\s+you\s+explain|can\s+you\s+clarify|please\s+clarify|clarify\s+the\s+question|what\s+does\s+that\s+mean|can\s+you\s+elaborate|don't\s+understand\s+the\s+question|didn't\s+get\s+the\s+question)\b", re.I),
    re.compile(r"(?:వివరించండి|ఏం\s*అడుగుతున్నారు|అర్థం\s*కాలేదు|క్లారిఫై|మరింత\s*వివరణ)", re.I),
    re.compile(r"(?:क्या\s*मतलब|स्पष्ट|समझाइए|प्रश्न\s*समझ\s*नहीं|विस्तार\s*से)", re.I),
]

REPEAT_PATTERNS = [
    re.compile(r"\b(?:repeat\s+(?:the\s+)?question|say\s+that\s+again|can\s+you\s+repeat|please\s+repeat|pardon\s+me|once\s+more|come\s+again)\b", re.I),
    re.compile(r"(?:మళ్లీ\s*చెప్పండి|మరోసారి\s*చెప్పండి|రిపీట్|మళ్ళీ\s*అడగండి)", re.I),
    re.compile(r"(?:दोहराएं|दोबारा\s*बताइए|फिर\s*से\s*बोलिए|एक\s*बार\s*फिर|सवाल\s*दोहराएं)", re.I),
]

UNCERTAINTY_PATTERNS = [
    re.compile(r"\b(?:i\s+don'?t\s+know|i\s+am\s+not\s+sure|i'?m\s+not\s+sure|no\s+idea|not\s+familiar|haven'?t\s+worked\s+with|not\s+certain|i\s+cannot\s+recall|forgot)\b", re.I),
    re.compile(r"(?:నాకు\s*తెలియదు|తెలియదు|ఖచ్చితంగా\s*తెలియదు|ఐడియా\s*లేదు|గుర్తు\s*లేదు|నాకు\s*రాదు)", re.I),
    re.compile(r"(?:मुझे\s*नहीं\s*पता|नहीं\s*पता|जानकारी\s*नहीं\s*है|मालूम\s*नहीं|याद\s*नहीं\s*आ\s*रहा|नहीं\s*आता)", re.I),
]

SKIP_PATTERNS = [
    re.compile(r"\b(?:skip\s+(?:this\s+)?(?:question)?|can\s+we\s+skip|move\s+to\s+next|next\s+question\s+please|pass\s+on\s+this|let'?s\s+skip)\b", re.I),
    re.compile(r"(?:దాటవేయండి|వదిలేయండి|తర్వాత\s*ప్రశ్నకు\s*వెళ్దాం|స్కిప్)", re.I),
    re.compile(r"(?:छोड़\s*दें|अगला\s*सवाल|आगे\s*बढ़ें|स्किप\s*करें|अगले\s*प्रश्न\s*पर\s*चलें)", re.I),
]


# ---------------------------------------------------------------------------
# 1. Competency Graph Definition
# ---------------------------------------------------------------------------

@dataclass
class CompetencyNode:
    concept: str
    track: str
    tier: str  # "fundamentals", "applied", "architecture"
    prerequisites: list[str] = field(default_factory=list)
    next_depth: list[str] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    description: str = ""


# Structured technical progression per track
COMPETENCY_GRAPHS: dict[str, dict[str, CompetencyNode]] = {
    "software": {
        "event_loop": CompetencyNode(
            concept="event_loop",
            track="software",
            tier="fundamentals",
            prerequisites=[],
            next_depth=["coroutines", "awaiting_io"],
            related_concepts=["async_frameworks"],
            description="Python asyncio event loop and single-threaded cooperative multitasking."
        ),
        "coroutines": CompetencyNode(
            concept="coroutines",
            track="software",
            tier="applied",
            prerequisites=["event_loop"],
            next_depth=["cpu_blocking_offload", "thread_pools"],
            related_concepts=["awaiting_io"],
            description="Coroutines, async/await syntax, and non-blocking I/O dispatch."
        ),
        "cpu_blocking_offload": CompetencyNode(
            concept="cpu_blocking_offload",
            track="software",
            tier="applied",
            prerequisites=["coroutines"],
            next_depth=["distributed_reliability"],
            related_concepts=["thread_pools", "process_pools"],
            description="Offloading CPU-bound tasks to process pools to avoid starving event loops."
        ),
        "distributed_reliability": CompetencyNode(
            concept="distributed_reliability",
            track="software",
            tier="architecture",
            prerequisites=["cpu_blocking_offload"],
            next_depth=["idempotency", "circuit_breakers"],
            related_concepts=["consensus_raft"],
            description="High-availability distributed architectures, failover, and retry policies."
        ),
        "idempotency": CompetencyNode(
            concept="idempotency",
            track="software",
            tier="architecture",
            prerequisites=["distributed_reliability"],
            next_depth=["consensus_raft"],
            related_concepts=["circuit_breakers", "cap_theorem"],
            description="Idempotent mutations, deduplication keys, and distributed consistency."
        ),
    },
    "agentic": {
        "tool_validation": CompetencyNode(
            concept="tool_validation",
            track="agentic",
            tier="fundamentals",
            prerequisites=[],
            next_depth=["tool_sandboxing", "permission_boundaries"],
            related_concepts=["prompt_templates"],
            description="Schema validation and parameter enforcement for agent tool calls."
        ),
        "tool_sandboxing": CompetencyNode(
            concept="tool_sandboxing",
            track="agentic",
            tier="applied",
            prerequisites=["tool_validation"],
            next_depth=["prompt_injection_defense", "multi_agent_coordination"],
            related_concepts=["permission_boundaries"],
            description="Sandboxed tool execution, human-in-the-loop approvals, and filesystem boundaries."
        ),
        "prompt_injection_defense": CompetencyNode(
            concept="prompt_injection_defense",
            track="agentic",
            tier="architecture",
            prerequisites=["tool_sandboxing"],
            next_depth=["drift_regression_testing"],
            related_concepts=["multi_agent_coordination"],
            description="Guarding agent runtimes against untrusted input injection and privilege escalation."
        ),
        "multi_agent_coordination": CompetencyNode(
            concept="multi_agent_coordination",
            track="agentic",
            tier="architecture",
            prerequisites=["tool_sandboxing"],
            next_depth=["drift_regression_testing"],
            related_concepts=["prompt_injection_defense"],
            description="State persistence, message routing, and distributed consensus in multi-agent swarms."
        ),
    },
    "ai": {
        "dataset_prep": CompetencyNode(
            concept="dataset_prep",
            track="ai",
            tier="fundamentals",
            prerequisites=[],
            next_depth=["model_validation", "training_loss"],
            related_concepts=["feature_engineering"],
            description="Data cleaning, leak prevention, and train/validation/test partitioning."
        ),
        "model_validation": CompetencyNode(
            concept="model_validation",
            track="ai",
            tier="applied",
            prerequisites=["dataset_prep"],
            next_depth=["production_serving", "drift_detection"],
            related_concepts=["evaluation_metrics"],
            description="Held-out validation, precision/recall trade-offs, and baseline comparisons."
        ),
        "production_serving": CompetencyNode(
            concept="production_serving",
            track="ai",
            tier="architecture",
            prerequisites=["model_validation"],
            next_depth=["drift_detection", "canary_mlops"],
            related_concepts=["gpu_quantization"],
            description="Latency budgets, GPU batching, model quantization, and production inference."
        ),
        "drift_detection": CompetencyNode(
            concept="drift_detection",
            track="ai",
            tier="architecture",
            prerequisites=["production_serving"],
            next_depth=["canary_mlops"],
            related_concepts=["production_serving"],
            description="Telemetry monitoring for data/concept drift and automated retraining triggers."
        ),
    },
}


# ---------------------------------------------------------------------------
# 2. Candidate Knowledge Model
# ---------------------------------------------------------------------------

@dataclass
class CompetencyState:
    concept: str
    status: str  # "demonstrated", "partially_demonstrated", "missing", "misconception", "skipped", "uncertain"
    evidence: list[str] = field(default_factory=list)
    missing_concepts: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    turn_indices: list[int] = field(default_factory=list)


class CandidateKnowledgeModel:
    """Maintains structured evidence of candidate technical competencies and decisions."""

    def __init__(
        self,
        role: str = "Software Engineer",
        track: str = "software",
        difficulty: str = "applied",
    ) -> None:
        self.role = role
        self.track = track if track in COMPETENCY_GRAPHS else "software"
        self.current_difficulty = difficulty
        self.competencies: dict[str, CompetencyState] = {}
        self.previous_questions: list[str] = []
        self.unresolved_followups: list[str] = []
        self.decisions: list[dict[str, Any]] = []
        self.current_interview_phase: str = "technical_probing"

    def record_answer_turn(
        self,
        turn_index: int,
        question_text: str,
        concept: str,
        feedback: dict[str, Any],
        transcript: str,
    ) -> None:
        """Update candidate knowledge state from an evaluated answer."""
        self.previous_questions.append(question_text)

        score = feedback.get("score", 0)
        dimensions = feedback.get("dimensions", {})
        tech_cov = dimensions.get("technical_coverage", 0)
        ev_score = dimensions.get("evidence", 0)
        risks = feedback.get("risks", []) or feedback.get("risk_flags", [])

        # Determine competency status
        if risks:
            status = "misconception"
            misconceptions = [r.get("explanation", "Conceptual error") for r in risks if isinstance(r, dict)]
        elif tech_cov >= 24 and score >= 65:
            status = "demonstrated"
            misconceptions = []
        elif tech_cov >= 12 or score >= 40:
            status = "partially_demonstrated"
            misconceptions = []
        else:
            status = "missing"
            misconceptions = []

        # Extract quote evidence
        evidence = []
        for f in risks:
            if isinstance(f, dict) and f.get("quote"):
                evidence.append(f["quote"])
        if not evidence and len(transcript) > 10:
            evidence.append(transcript[:100].strip())

        missing = feedback.get("missing_concepts", [])

        state = self.competencies.get(concept)
        if state is None:
            state = CompetencyState(
                concept=concept,
                status=status,
                evidence=evidence,
                missing_concepts=missing,
                misconceptions=misconceptions,
                confidence=min(1.0, score / 100.0),
                turn_indices=[turn_index],
            )
            self.competencies[concept] = state
        else:
            state.status = status
            state.evidence.extend(evidence)
            state.missing_concepts = missing
            state.misconceptions.extend(misconceptions)
            state.confidence = (state.confidence + min(1.0, score / 100.0)) / 2.0
            state.turn_indices.append(turn_index)

        # Record auditable decision
        self.decisions.append({
            "turn_index": turn_index,
            "concept": concept,
            "status": status,
            "score": score,
            "resulting_difficulty": self.current_difficulty,
            "action": "answer_evaluated",
        })

    def record_dialogue_event(
        self,
        turn_index: int,
        intent: str,
        concept: str,
        note: str = "",
    ) -> None:
        """Record non-grading conversational interactions (clarification, repeat, skip, uncertainty)."""
        if intent == INTENT_UNCERTAINTY:
            state = self.competencies.get(concept)
            if state is None:
                state = CompetencyState(
                    concept=concept,
                    status="uncertain",
                    missing_concepts=[concept],
                    confidence=0.1,
                    turn_indices=[turn_index],
                )
                self.competencies[concept] = state
            else:
                state.status = "uncertain"

        self.decisions.append({
            "turn_index": turn_index,
            "concept": concept,
            "status": intent,
            "score": None,
            "action": f"dialogue_{intent}",
            "note": note,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "track": self.track,
            "current_difficulty": self.current_difficulty,
            "current_interview_phase": self.current_interview_phase,
            "competencies": {k: asdict(v) for k, v in self.competencies.items()},
            "previous_questions": self.previous_questions,
            "unresolved_followups": self.unresolved_followups,
            "decisions": self.decisions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateKnowledgeModel:
        model = cls(
            role=data.get("role", "Software Engineer"),
            track=data.get("track", "software"),
            difficulty=data.get("current_difficulty", "applied"),
        )
        model.current_interview_phase = data.get("current_interview_phase", "technical_probing")
        model.previous_questions = data.get("previous_questions", [])
        model.unresolved_followups = data.get("unresolved_followups", [])
        model.decisions = data.get("decisions", [])
        comps = data.get("competencies", {})
        for k, v in comps.items():
            model.competencies[k] = CompetencyState(**v)
        return model


# ---------------------------------------------------------------------------
# 3. Dialogue Policy & Intent Handling
# ---------------------------------------------------------------------------

class DialoguePolicy:
    """Manages conversational turn intent and natural dialogue transitions."""

    @staticmethod
    def classify_intent(transcript: str) -> str:
        """Classify candidate utterance into conversational intent."""
        cleaned = transcript.strip()
        if not cleaned:
            return INTENT_ANSWER

        words = cleaned.split()

        # Uncertainty: short candidate admissions of uncertainty
        for pat in UNCERTAINTY_PATTERNS:
            if pat.search(cleaned) and len(words) <= 15:
                return INTENT_UNCERTAINTY

        # Clarification request
        for pat in CLARIFICATION_PATTERNS:
            if pat.search(cleaned) and (len(words) <= 16 or cleaned.endswith("?")):
                return INTENT_CLARIFICATION

        # Repetition request
        for pat in REPEAT_PATTERNS:
            if pat.search(cleaned) and len(words) <= 12:
                return INTENT_REPEAT

        # Skip request
        for pat in SKIP_PATTERNS:
            if pat.search(cleaned) and len(words) <= 10:
                return INTENT_SKIP

        return INTENT_ANSWER

    @staticmethod
    def generate_clarification(question_text: str, language: str) -> str:
        """Explain the question more clearly without grading it as an answer."""
        if language == "te-IN":
            return (
                f"ఈ ప్రశ్నకు మరింత స్పష్టత: మీరు మీ ప్రాజెక్ట్‌లో చేసిన ఖచ్చితమైన పని మరియు "
                f"నిర్ణయాలను వివరించండి. ప్రశ్న: {question_text}"
            )
        elif language == "hi-IN":
            return (
                f"इस प्रश्न का स्पष्टीकरण: आप अपने प्रोजेक्ट में किए गए वास्तविक कार्य और "
                f"तकनीकी निर्णय को समझाइए। प्रश्न है: {question_text}"
            )
        return (
            f"Here is what I'm asking: Focus on the specific implementation details, trade-offs, "
            f"and practical tests from your project. Specifically: {question_text}"
        )

    @staticmethod
    def generate_repeat(question_text: str, language: str) -> str:
        """Politely repeat the current question."""
        if language == "te-IN":
            return f"తప్పకుండా, ప్రశ్నను మళ్లీ చెబుతున్నాను: {question_text}"
        elif language == "hi-IN":
            return f"ज़रूर, मैं सवाल दोहराता हूँ: {question_text}"
        return f"Certainly, let me repeat the question: {question_text}"

    @staticmethod
    def generate_uncertainty_pivot(language: str) -> str:
        """Encouraging pivot when candidate acknowledges uncertainty."""
        if language == "te-IN":
            return "సమస్య లేదు! దీని ప్రాథమిక విధానం నుండి పరిశీలిద్దాం."
        elif language == "hi-IN":
            return "कोई बात नहीं! आइए इसके बुनियादी पहलू से शुरुआत करते हैं."
        return "That's completely fine! Let's explore the foundational concept instead."

    @staticmethod
    def generate_skip_ack(language: str) -> str:
        """Acknowledge skipping to next topic."""
        if language == "te-IN":
            return "అలాగే, ఈ ప్రశ్నను దాటవేస్తున్నాం. తర్వాతి అంశానికి వెళ్దాం."
        elif language == "hi-IN":
            return "ठीक है, इस प्रश्न को छोड़ते हैं। आइए अगले विषय पर चलते हैं."
        return "Understood. Moving on to our next technical topic."


# ---------------------------------------------------------------------------
# 4. Graph-Guided Question Selection
# ---------------------------------------------------------------------------

def select_graph_followup(
    knowledge_model: CandidateKnowledgeModel,
    language: str,
    feedback: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Select the next question using CompetencyGraph and CandidateKnowledgeModel.

    Guarantees:
    - Never jumps randomly across unrelated concepts.
    - Misconceptions de-escalate to foundational prerequisite concepts.
    - Strong answers escalate along the graph depth.
    - Already asked questions are never repeated.
    """
    track = knowledge_model.track
    graph = COMPETENCY_GRAPHS.get(track, COMPETENCY_GRAPHS["software"])

    from adaptive import SOCRATIC_BANK, DIFFICULTY_LEVELS, REASONS

    has_misconception = bool(
        feedback.get("risks") or feedback.get("risk_flags") or feedback.get("misconceptions")
    )
    score = feedback.get("score", 50)

    # 1. Determine target difficulty
    if has_misconception:
        target_tier = "fundamentals"
        focus = "technical"
    elif score >= 75:
        target_tier = "architecture"
        focus = "tradeoff"
    elif score >= 40:
        target_tier = "applied"
        focus = "evidence"
    else:
        target_tier = "fundamentals"
        focus = "clarity"

    knowledge_model.current_difficulty = target_tier

    # 2. Select appropriate question from SOCRATIC_BANK
    tier_bank = SOCRATIC_BANK.get(track, SOCRATIC_BANK["software"]).get(
        target_tier, SOCRATIC_BANK["software"]["applied"]
    )
    spec = dict(tier_bank.get(focus, tier_bank["technical"]))
    spec["level"] = target_tier
    spec["focus"] = focus
    spec["question_type"] = "graph_guided_socratic"

    # 3. Transparent reason
    if has_misconception and "misconception" in REASONS:
        reason_text = REASONS["misconception"].get(language, REASONS["misconception"]["en-IN"])
    else:
        reason_text = REASONS.get(focus, {}).get(language, REASONS[focus]["en-IN"])

    return spec, reason_text, focus
