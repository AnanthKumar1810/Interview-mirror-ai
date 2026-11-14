"""Bounded, explainable personalization module for InterviewMirror AI.

Extracts key competencies from candidate resume text and inspects public
GitHub repository metadata within strict security and resource bounds.
Produces deterministic question seeds without external LLM dependencies.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("interviewmirror.personalization")

MAX_RESUME_CHARS = 50_000
GITHUB_REQUEST_TIMEOUT = 3.0
GITHUB_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+$")
GITHUB_USER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

INTRODUCE_YOURSELF_QUESTION = {
    "en-IN": "Please introduce yourself, and tell me briefly about your technical background and what you are passionate about building.",
    "te-IN": "దయచేసి మీ గురించి పరిచయం చేసుకోండి, మీ సాంకేతిక నేపథ్యం మరియు మీరు నిర్మించడానికి ఇష్టపడే ప్రాజెక్ట్‌ల గురించి చెప్పండి.",
    "hi-IN": "कृपया अपना परिचय दीजिए, अपनी तकनीकी पृष्ठभूमि और अपने पसंदीदा प्रोजेक्ट्स के बारे में संक्षेप में बताइए।",
    "keywords": ["experience", "background", "project", "technology", "built", "student", "developer", "engineer", "ప్రాజెక్ట్", "అనుభవం", "పరిచయం", "अनुभव", "प्रोजेक्ट", "परिचय"],
    "concepts": [
        ("background & role", ["experience", "background", "student", "engineer", "developer", "college", "graduate", "అనుభవం", "నేపథ్యం", "విద్యార్థి", "अनुभव", "इंजीनियर"]),
        ("technologies & skills", ["python", "code", "tech", "project", "data", "ai", "software", "ప్రాజెక్ట్", "సాంకేతిక", "సమస్య", "तकनीक", "प्रोजेक्ट"]),
        ("passion & goals", ["build", "built", "passion", "work", "learn", "interest", "చేసాను", "నేర్చుకో", "ఆసక్తి", "सीखना", "बनाया", "रुचि"]),
    ],
}

KNOWN_SKILLS = {
    "agentic": ["langchain", "autogen", "crewai", "tools", "mcp", "agents", "function calling", "guardrails", "docker"],
    "ai": ["pytorch", "tensorflow", "transformers", "huggingface", "scikit-learn", "pandas", "numpy", "classification", "cv", "nlp", "llm"],
    "software": ["python", "fastapi", "flask", "django", "nodejs", "react", "postgresql", "redis", "kubernetes", "sqlite", "git", "ci/cd", "pytest"],
}


def parse_github_slug(input_str: str) -> str | None:
    """Extract and validate owner/repo slug from URL or bare string.

    Guards strictly against SSRF, internal IP addresses, and command injection.
    """
    cleaned = input_str.strip()
    if not cleaned:
        return None

    # Handle https://github.com/owner/repo or http://
    if "github.com/" in cleaned:
        parts = [p for p in cleaned.split("github.com/")[-1].split("/") if p]
        if len(parts) >= 2:
            repo_part = parts[1].removesuffix(".git")
            cleaned = f"{parts[0]}/{repo_part}"

    # Strip trailing slashes or .git
    cleaned = cleaned.removesuffix(".git").rstrip("/")

    if GITHUB_SLUG_PATTERN.match(cleaned):
        # Verify neither component is suspicious
        owner, repo = cleaned.split("/", 1)
        if owner.lower() in ("localhost", "127.0.0.1", "0.0.0.0") or repo.lower() in ("localhost", "127.0.0.1"):
            return None
        return cleaned

    return None


def parse_github_target(input_str: str) -> tuple[str, str] | tuple[None, None]:
    """Extract and validate GitHub username or owner/repo slug."""
    cleaned = input_str.strip()
    if not cleaned:
        return None, None
    if "github.com/" in cleaned:
        parts = [p for p in cleaned.split("github.com/")[-1].split("/") if p]
        if len(parts) >= 2:
            repo_part = parts[1].removesuffix(".git")
            cleaned = f"{parts[0]}/{repo_part}"
        elif len(parts) == 1:
            cleaned = parts[0].removesuffix(".git")
    cleaned = cleaned.removesuffix(".git").rstrip("/")
    if "/" in cleaned:
        slug = parse_github_slug(cleaned)
        return ("repo", slug) if slug else (None, None)
    if GITHUB_USER_PATTERN.match(cleaned):
        if cleaned.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
            return None, None
        return ("user", cleaned)
    return None, None


def extract_resume_profile(text: str) -> dict[str, Any]:
    """Safely extract skills, project hints, and suggested track from resume text.

    Truncates input to MAX_RESUME_CHARS to prevent CPU backtracking or memory exhaustion.
    """
    if not text:
        return {
            "skills": [],
            "suggested_track": "software",
            "project_highlights": [],
            "char_count": 0,
        }

    bounded_text = text[:MAX_RESUME_CHARS]
    lowered = bounded_text.lower()

    # Detect skills across domain tracks
    detected_skills: list[str] = []
    track_scores = {"agentic": 0, "ai": 0, "software": 0}

    for track, skills in KNOWN_SKILLS.items():
        for skill in skills:
            pattern = r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])"
            if re.search(pattern, lowered):
                detected_skills.append(skill)
                track_scores[track] += 1

    # Determine recommended track
    suggested_track = max(track_scores, key=lambda k: (track_scores[k], k == "software"))
    if track_scores[suggested_track] == 0:
        suggested_track = "software"

    # Extract project highlights (bullet points or lines containing 'project', 'built', 'developed')
    highlights = []
    achievements = []
    education = []
    lines = [line.strip("-* \t\r") for line in bounded_text.splitlines() if line.strip()]

    achievement_triggers = (
        "award", "winner", "won", "first place", "1st", "2nd", "3rd", "finalist", "runner up",
        "hackathon", "ranked", "rank", "published", "publication", "patent", "certified", "certification",
        "scholarship", "distinction", "fellowship", "lead", "optimized", "increased", "reduced",
        "improved", "honors", "gold", "silver", "top 1", "medal", "fellow", "mentored", "achieved",
        "solved", "percentile", "score", "cleared", "selected", "accelerated", "scaled", "automated", "shipped"
    )
    education_triggers = (
        "bachelor", "master", "b.tech", "m.tech", "degree", "university",
        "college", "cgpa", "gpa", "internship", "graduate"
    )

    # Split lines by newline and common delimiters (;, •, |)
    raw_segments = []
    for line in bounded_text.splitlines():
        if ";" in line or "•" in line or "|" in line:
            for sub in re.split(r"[;•|]", line):
                if sub.strip():
                    raw_segments.append(sub.strip("-* \t\r"))
        elif line.strip():
            raw_segments.append(line.strip("-* \t\r"))

    for line in raw_segments:
        if len(line) < 10 or len(line) > 250:
            continue
        line_lower = line.lower()
        if any(trig in line_lower for trig in achievement_triggers):
            achievements.append(line)
        elif any(trig in line_lower for trig in education_triggers):
            education.append(line)
        elif any(trigger in line_lower for trigger in ("built", "developed", "implemented", "designed", "project", "system")):
            highlights.append(line)

    return {
        "skills": sorted(list(set(detected_skills))),
        "suggested_track": suggested_track,
        "track_scores": track_scores,
        "project_highlights": highlights[:4],
        "achievements": achievements[:4],
        "education": education[:3],
        "char_count": len(bounded_text),
    }


def inspect_github_repo(repo_url_or_slug: str, timeout_seconds: float = GITHUB_REQUEST_TIMEOUT) -> dict[str, Any]:
    """Perform bounded, read-only inspection of a public GitHub repository.

    Supports GITHUB_TOKEN from .env for high rate limits.
    Fails gracefully to a structured fallback if offline, blocked, or rate limited.
    """
    slug = parse_github_slug(repo_url_or_slug)
    if not slug:
        return {
            "valid": False,
            "error": "Invalid GitHub repository identifier",
            "slug": None,
            "languages": [],
            "topics": [],
        }

    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "User-Agent": "InterviewMirror-Personalization/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/repos/{slug}"
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                return {
                    "valid": True,
                    "kind": "repo",
                    "slug": slug,
                    "name": data.get("name", ""),
                    "description": data.get("description") or "",
                    "primary_language": data.get("language") or "Python",
                    "topics": data.get("topics") or [],
                    "stars": data.get("stargazers_count", 0),
                    "status": "live",
                    "projects": [{
                        "name": data.get("name", ""),
                        "description": data.get("description") or "",
                        "language": data.get("language") or "Python",
                        "topics": data.get("topics") or [],
                        "stars": data.get("stargazers_count", 0),
                    }],
                }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.info("GitHub API fetch fallback for %s: %s", slug, exc)

    # Clean deterministic fallback if offline, rate limited, or private
    owner, repo_name = slug.split("/", 1)
    return {
        "valid": True,
        "kind": "repo",
        "slug": slug,
        "name": repo_name,
        "description": f"Public repository by {owner}",
        "primary_language": "Python",
        "topics": ["developer-tools"],
        "stars": 0,
        "status": "fallback",
        "projects": [{"name": repo_name, "description": f"Public repository by {owner}", "language": "Python", "topics": ["developer-tools"], "stars": 0}],
    }


def inspect_github_user(username: str, timeout_seconds: float = GITHUB_REQUEST_TIMEOUT) -> dict[str, Any]:
    """Inspect public repositories for a GitHub user profile."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "User-Agent": "InterviewMirror-Personalization/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=6"
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status == 200:
                repos = json.loads(resp.read().decode("utf-8", errors="replace"))
                projects = []
                langs = []
                for r in repos:
                    if not r.get("fork"):
                        lang = r.get("language") or "Python"
                        langs.append(lang)
                        projects.append({
                            "name": r.get("name", ""),
                            "description": r.get("description") or "",
                            "language": lang,
                            "topics": r.get("topics") or [],
                            "stars": r.get("stargazers_count", 0),
                        })
                projects.sort(key=lambda p: (bool(p["description"]), p["stars"]), reverse=True)
                best = projects[0] if projects else {"name": "portfolio-project", "description": "Candidate technical repository", "language": "Python", "topics": [], "stars": 0}
                primary_lang = max(set(langs), key=langs.count) if langs else "Python"
                return {
                    "valid": True,
                    "kind": "user",
                    "username": username,
                    "slug": f"{username}/{best['name']}",
                    "name": best["name"],
                    "description": best["description"] or f"Public repository by {username}",
                    "primary_language": best["language"] or primary_lang,
                    "topics": best.get("topics", []),
                    "stars": best.get("stars", 0),
                    "status": "live",
                    "projects": projects,
                }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.info("GitHub user repos fetch fallback for %s: %s", username, exc)

    return {
        "valid": True,
        "kind": "user",
        "username": username,
        "slug": f"{username}/portfolio-project",
        "name": "portfolio-project",
        "description": f"Software project by {username}",
        "primary_language": "Python",
        "topics": ["software"],
        "stars": 0,
        "status": "fallback",
        "projects": [{"name": "portfolio-project", "description": f"Software project by {username}", "language": "Python", "topics": ["software"], "stars": 0}],
    }


def inspect_github_target(target: str, timeout_seconds: float = GITHUB_REQUEST_TIMEOUT) -> dict[str, Any]:
    """Inspect GitHub target as either repository slug or username."""
    if not target or not target.strip():
        return {"valid": False, "error": "Empty GitHub target", "slug": None, "languages": [], "topics": []}
    slug = parse_github_slug(target)
    if slug:
        return inspect_github_repo(slug, timeout_seconds=timeout_seconds)
    kind, ident = parse_github_target(target)
    if kind == "user":
        return inspect_github_user(ident, timeout_seconds=timeout_seconds)
    return {
        "valid": False,
        "error": "Invalid GitHub repository or username identifier",
        "slug": None,
        "languages": [],
        "topics": [],
    }


def personalize_question_seed(
    track: str,
    language: str,
    resume_text: str | None = None,
    github_repo: str | None = None,
    base_question: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synthesize a personalized initial interview seed.

    Preserves Gnani-only model constraint: uses deterministic templates and
    extracted profile tokens without generative LLM hallucination.
    """
    resume_profile = extract_resume_profile(resume_text or "")
    github_profile = inspect_github_target(github_repo) if github_repo else None

    # Identify primary technical anchor and match GitHub projects to resume
    anchor_tech = ""
    matched_repo_name = ""
    if github_profile and github_profile.get("valid"):
        projects = github_profile.get("projects", [])
        resume_lower = (resume_text or "").lower()
        matched_repo = None
        if resume_lower and projects:
            for p in projects:
                name_clean = p["name"].lower().replace("-", " ").replace("_", " ")
                if p["name"].lower() in resume_lower or name_clean in resume_lower:
                    matched_repo = p
                    break
                if any(topic.lower() in resume_lower for topic in p.get("topics", [])):
                    matched_repo = p
                    break
        if matched_repo:
            matched_repo_name = matched_repo["name"]
            anchor_tech = matched_repo.get("language") or "Python"
        elif github_profile.get("name"):
            matched_repo_name = github_profile["name"]
            anchor_tech = github_profile.get("primary_language") or "Python"

    if not anchor_tech:
        if resume_profile.get("skills"):
            anchor_tech = resume_profile["skills"][0].capitalize()
        else:
            anchor_tech = "Python"

    project_context = ""
    if matched_repo_name:
        project_context = f"in your '{matched_repo_name}' project from your resume"
    elif resume_profile.get("project_highlights"):
        project_context = "in your primary portfolio project from your resume"
    else:
        project_context = "in a technical project you built"

    templates = {
        "en-IN": {
            "agentic": f"Tell me about an agent workflow or tool pipeline you implemented {project_context} using {anchor_tech}. What core problem did it solve, and how did you prevent unreliable actions?",
            "ai": f"Describe a model or machine learning pipeline you developed {project_context} using {anchor_tech}. What problem did it address, and how did you evaluate its performance?",
            "software": f"Walk me through a complex bug or distributed systems challenge you investigated {project_context} using {anchor_tech}. What was the root cause, and how did you verify the fix?",
        },
        "te-IN": {
            "agentic": f"{anchor_tech} ఉపయోగించి మీరు {project_context} రూపొందించిన ఏజెంట్ వర్క్‌ఫ్లో గురించి చెప్పండి. అది ఏ సమస్యను పరిష్కరించింది, లోపాలు రాకుండా ఏ నియంత్రణలు పెట్టారు?",
            "ai": f"{anchor_tech} తో {project_context} మీరు శిక్షణ ఇచ్చిన మోడల్ లేదా ప్రాజెక్ట్ గురించి వివరించండి. దాని పనితీరును ఎలా కొలిచారు?",
            "software": f"{anchor_tech} ఉపయోగించి {project_context} మీరు పరిశోధించిన ఒక సంక్లిష్ట బగ్ గురించి చెప్పండి. అసలు లోపం ఏమిటి, దాన్ని ఎలా పరిష్కరించారు?",
        },
        "hi-IN": {
            "agentic": f"{anchor_tech} का उपयोग करके {project_context} बनाए गए एजेंट वर्कफ़्लो के बारे में बताइए। उसने क्या समस्या हल की और अनपेक्षित क्रियाओं को कैसे रोका?",
            "ai": f"{anchor_tech} के साथ {project_context} आपके द्वारा बनाए गए मॉडल के बारे में समझाइए। आपने इसके प्रदर्शन का मूल्यांकन कैसे किया?",
            "software": f"{anchor_tech} का उपयोग करके {project_context} जाँचे गए एक जटिल बग के बारे में बताइए। मूल कारण क्या था और आपने समाधान की पुष्टि कैसे की?",
        },
    }

    localized_text = templates.get(language, templates["en-IN"]).get(track, templates["en-IN"]["software"])

    # Optional achievement & background deep-dive question
    achievement_q = None
    ach_text = ""
    if resume_profile.get("achievements"):
        ach_text = resume_profile["achievements"][0].strip("-* \t\r")
    elif len(resume_profile.get("project_highlights", [])) >= 2:
        ach_text = resume_profile["project_highlights"][1].strip("-* \t\r")
    elif resume_profile.get("education"):
        ach_text = resume_profile["education"][0].strip("-* \t\r")

    if ach_text:
        ach_templates = {
            "en-IN": f"Your background highlights: '{ach_text}'. Can you explain the technical decisions you made to achieve this milestone, and what measurable impact it produced?",
            "te-IN": f"మీ నేపథ్యం '{ach_text}' గురించి పేర్కొన్నారు. దీన్ని సాధించడానికి మీరు ఎలాంటి సాంకేతిక నిర్ణయాలు తీసుకున్నారు, దాని ప్రభావాన్ని ఎలా కొలిచారు?",
            "hi-IN": f"आपकी पृष्ठभूमि में '{ach_text}' का उल्लेख है। इस उपलब्धि को हासिल करने के लिए आपने क्या तकनीकी निर्णय लिए और इसके प्रभाव को कैसे मापा?",
        }
        achievement_q = {
            "en-IN": ach_templates["en-IN"],
            "te-IN": ach_templates["te-IN"],
            "hi-IN": ach_templates["hi-IN"],
            "text": ach_templates.get(language, ach_templates["en-IN"]),
            "keywords": ["achievement", "impact", "metric", "result", "milestone", "సాధన", "ఫలితం", "उपलब्धि", "परिणाम"],
            "concepts": [
                ("technical approach", ["approach", "decision", "built", "implemented", "architecture", "strategy", "designed", "code", "నిర్ణయం", "విధానం", "పద్ధతి", "दृष्टिकोण", "रणनीति"]),
                ("challenge & resolution", ["challenge", "problem", "solve", "fixed", "bottleneck", "obstacle", "issue", "tradeoff", "సవాలు", "పరిష్కారం", "ఇబ్బంది", "चुनौती", "समस्या"]),
                ("measurable impact", ["impact", "metric", "percent", "scale", "result", "speedup", "latency", "accuracy", "reduced", "increased", "efficiency", "విలువ", "ఫలితం", "శాతం", "प्रभाव", "परिणाम"]),
            ],
            "achievement_highlight": ach_text,
        }

    # Default concepts for turn
    default_concepts = [
        ("project / tool", [anchor_tech.lower(), "project", "tool", "workflow", "మోడల్", "ప్రాజెక్ట్", "मॉडल", "टूल"]),
        ("problem / mechanism", ["problem", "data", "bug", "error", "సమస్య", "లోపం", "समस्या", "दोष"]),
        ("validation / outcome", ["test", "verify", "result", "metric", "పరీక్ష", "ఫలితం", "परीक्षण", "परिणाम"]),
    ]

    return {
        "text": localized_text,
        language: localized_text,
        "track": track,
        "language": language,
        "anchor_tech": anchor_tech,
        "project_context": project_context,
        "concepts": default_concepts,
        "resume_profile": resume_profile,
        "github_profile": github_profile,
        "achievement_question": achievement_q,
        "personalization_applied": bool(resume_text or github_repo),
    }
