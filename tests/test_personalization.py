"""Unit tests for Phase 8: Bounded Personalization (Resume & GitHub)."""
import pytest
from personalization import (
    parse_github_slug,
    extract_resume_profile,
    inspect_github_repo,
    personalize_question_seed,
    MAX_RESUME_CHARS,
)


def test_parse_github_slug_valid_and_sanitization():
    assert parse_github_slug("AnanthKumar1810/Interview-mirror-ai") == "AnanthKumar1810/Interview-mirror-ai"
    assert parse_github_slug("https://github.com/pytorch/pytorch.git") == "pytorch/pytorch"
    assert parse_github_slug("https://github.com/fastapi/fastapi/") == "fastapi/fastapi"

    # Security rejections
    assert parse_github_slug("localhost/repo") is None
    assert parse_github_slug("127.0.0.1/repo") is None
    assert parse_github_slug("../../../etc/passwd") is None
    assert parse_github_slug("owner/repo; cat /etc/shadow") is None
    assert parse_github_slug("https://evil.com/owner/repo") is None
    assert parse_github_slug("") is None


def test_extract_resume_profile_bounds_and_skills():
    resume_text = (
        "Experienced Engineer with deep experience in Python, PyTorch, and Transformers.\n"
        "- Built an automated classification pipeline using Scikit-Learn.\n"
        "- Designed real-time monitoring with Pandas and Numpy.\n"
    )
    profile = extract_resume_profile(resume_text)
    assert profile["suggested_track"] == "ai"
    assert "pytorch" in profile["skills"]
    assert "transformers" in profile["skills"]
    assert len(profile["project_highlights"]) >= 1

    # Large input truncation test
    huge_text = "Python " * 20_000  # 140,000 characters
    profile_huge = extract_resume_profile(huge_text)
    assert profile_huge["char_count"] == MAX_RESUME_CHARS
    assert "python" in profile_huge["skills"]


def test_inspect_github_repo_offline_fallback():
    # Calling with dummy repo should safely fallback without raising
    result = inspect_github_repo("octocat/Hello-World", timeout_seconds=0.5)
    assert result["valid"] is True
    assert result["slug"] == "octocat/Hello-World"
    assert "primary_language" in result
    assert result["status"] in ("live", "fallback")

    # Invalid slug
    invalid = inspect_github_repo("invalid-slug")
    assert invalid["valid"] is False


@pytest.mark.parametrize("language", ["en-IN", "te-IN", "hi-IN"])
@pytest.mark.parametrize("track", ["agentic", "ai", "software"])
def test_personalize_question_seed_deterministic(language, track):
    resume_text = "Built a distributed REST backend using FastAPI and Docker."
    seed = personalize_question_seed(
        track=track,
        language=language,
        resume_text=resume_text,
        github_repo="owner/my-backend",
    )
    assert seed["personalization_applied"] is True
    assert seed["language"] == language
    assert seed["track"] == track
    assert len(seed["concepts"]) == 3
    assert seed["text"]
    assert "FastAPI" in seed["text"] or "Python" in seed["text"] or "my-backend" in seed["text"]


def test_resume_achievements_extraction_and_question_generation():
    resume = (
        "B.Tech Computer Science from State University, 9.4 CGPA.\n"
        "Winner of National AI Hackathon 2025; ranked top 1 percent among 4000 participants.\n"
        "Published paper on automated software vulnerability repair in IEEE.\n"
        "Built bug-fixer: SWE-bench autonomous agent using Python and Docker.\n"
        "Reduced benchmark repair latency by 45 percent and improved fix accuracy to 78 percent.\n"
    )
    profile = extract_resume_profile(resume)
    assert len(profile["achievements"]) >= 2
    assert any("Hackathon" in a or "Winner" in a for a in profile["achievements"])
    assert any("B.Tech" in e or "CGPA" in e for e in profile["education"])

    seed = personalize_question_seed("agentic", "en-IN", resume_text=resume, github_repo="AnanthKumar1810/bug-fixer")
    assert seed["achievement_question"] is not None
    ach_q = seed["achievement_question"]
    assert "en-IN" in ach_q
    assert "te-IN" in ach_q
    assert "hi-IN" in ach_q
    assert len(ach_q["concepts"]) == 3


def test_interview_state_machine_full_personalized_progression():
    from interview_state import InterviewStateMachine
    from personalization import INTRODUCE_YOURSELF_QUESTION

    resume = (
        "Winner of Smart India Hackathon 2024.\n"
        "Built bug-fixer: automated SWE-bench repair in Python.\n"
        "Reduced test failure diagnosis time by 60 percent across 200 repositories.\n"
    )
    seed = personalize_question_seed("agentic", "en-IN", resume_text=resume, github_repo="AnanthKumar1810/bug-fixer")

    # Start with mandatory Introduction
    sm = InterviewStateMachine(
        track="agentic",
        language="en-IN",
        initial_question_spec=INTRODUCE_YOURSELF_QUESTION,
        max_questions=3,
    )
    sm.personalized_seed = seed
    assert sm.current_question_spec() == INTRODUCE_YOURSELF_QUESTION

    # Q1: Candidate introduces themselves
    res1 = sm.process_candidate_utterance(
        "Hello, I am a software engineering student. I have experience building AI developer tools in Python and I am passionate about autonomous agent workflows."
    )
    assert res1["action"] == "evaluate"
    assert sm.question_index == 1
    # Q2 should now be the personalized project question
    assert sm.pending_kind == "personalized_project"
    assert "bug-fixer" in sm.current_question_text() or "Python" in sm.current_question_text()

    # Q2: Candidate explains their project
    res2 = sm.process_candidate_utterance(
        "In the bug-fixer project, I built a Python agent that reproduces bugs using Docker containers. I implemented guardrails and sandbox permissions to prevent destructive bash commands."
    )
    assert res2["action"] == "evaluate"
    assert sm.question_index == 2
    # Q3 should now be the personalized achievement question
    assert sm.pending_kind == "personalized_achievement"
    assert "Smart India Hackathon" in sm.current_question_text() or "achievement" in sm.current_question_spec().get("keywords", [])

    # Q3: Candidate details their achievement and measurable impact
    res3 = sm.process_candidate_utterance(
        "For the hackathon, our technical decision was to use AST-level patch filtering. We solved the timeout bottleneck by parallelizing unit test execution across 4 workers, which reduced latency by 60 percent and secured first place."
    )
    assert res3["action"] == "evaluate"
    assert sm.question_index == 3
    assert res3["completed"] is True
    sm.end_interview()
    assert sm.is_complete is True

    # Validate that achievement question evaluated concrete metrics and technical decisions
    q3_feedback = sm.answers[2]["feedback"]
    assert q3_feedback["score"] >= 60
    assert q3_feedback["dimensions"]["technical_coverage"] >= 20
    assert q3_feedback["dimensions"]["evidence"] >= 12

