"""Optional, bounded Gemini question refinement over verified profile evidence.

Gnani remains the only live speech provider. Failure or quota exhaustion keeps
the deterministic question unchanged.
"""
from __future__ import annotations

import json
import os

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"


def refine_personalized_seed(seed: dict | None, role: str) -> dict | None:
    if not seed or not os.getenv("GEMINI_API_KEY", "").strip():
        return seed
    resume = seed.get("resume_profile") or {}
    github = seed.get("github_profile") or {}
    source = {
        "role": role[:100],
        "track": seed.get("track"),
        "language": seed.get("language"),
        "resume_skills": resume.get("skills", [])[:12],
        "resume_projects": resume.get("project_highlights", [])[:3],
        "resume_achievements": resume.get("achievements", [])[:2],
        "verified_github": {
            "name": github.get("name"),
            "description": github.get("description"),
            "language": github.get("primary_language"),
            "topics": github.get("topics", [])[:8],
        } if github.get("status") == "live" else None,
        "project_question_to_refine": seed.get("text"),
    }
    instruction = (
        "You are a senior technical interviewer. Write exactly one concise interview question "
        "in the requested language. Use ONLY the evidence in the JSON below. "
        "Probe a specific technical decision in the candidate's project. "
        "Preserve the technical scope of project_question_to_refine. "
        "Do not invent a repository, skill, metric, accomplishment, employer, or degree. "
        "Return a JSON object with one nonempty string key: question.\n"
        + json.dumps(source, ensure_ascii=False)
    )
    try:
        response = httpx.post(
            GEMINI_URL,
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
            json={"contents": [{"role": "user", "parts": [{"text": instruction}]}],
                  "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 500}},
            timeout=15.0,
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        proposal = json.loads("".join(part.get("text", "") for part in parts))
        project = proposal.get("question")
        if not isinstance(project, str) or not 25 <= len(project) <= 400:
            return seed
        revised = dict(seed)
        revised["text"] = project.strip()
        revised[seed["language"]] = project.strip()
        revised["question_source"] = "gemini_verified_profile"
        return revised
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return seed
