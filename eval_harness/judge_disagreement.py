"""Audit experimental judge scores without changing the live practice score."""
from robust_evaluation import evaluate_for_app


def local_ollama_judge(transcript: str, question: dict, language: str, *, model="qwen2.5:3b"):
    """Experimental localhost-only judge. Its score is never the practice score."""
    import json
    from urllib.request import Request, build_opener, ProxyHandler
    prompt = ("Score the candidate answer from 0 to 100 for technical relevance. "
              "Return JSON with score, quote (an EXACT nonempty substring of the answer), "
              "and reason. Do not invent facts.\n"
              f"Question: {question.get('text', '')}\nAnswer: {transcript}")
    payload = {"model": model, "stream": False, "format": "json",
               "messages": [{"role": "user", "content": prompt}]}
    request = Request("http://127.0.0.1:11434/api/chat", json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=120) as response:
        envelope = json.load(response)
    return json.loads(envelope["message"]["content"])


def compare_judge(transcript: str, question: dict, language: str, judge):
    rubric = evaluate_for_app(transcript, question, language)
    proposal = judge(transcript, question, language)
    score = proposal.get("score") if isinstance(proposal, dict) else None
    quote = proposal.get("quote") if isinstance(proposal, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        raise ValueError("Judge must return a numeric score from 0 to 100")
    if not isinstance(quote, str) or not quote.strip() or quote not in transcript:
        raise ValueError("Judge must quote exact answer text as evidence")
    return {"practice_score": rubric["score"], "judge_score": score,
            "difference": score - rubric["score"], "judge_quote": quote,
            "judge_reason": str(proposal.get("reason", "")),
            "status": "review_required" if score != rubric["score"] else "agreement_unvalidated",
            "authoritative_method": rubric["method"]}

