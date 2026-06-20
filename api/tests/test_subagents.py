"""Regression: subagents must not mistake echoed prompt JSON for a real result.

In mock mode the LLM echoes the prompt, which contains the profile/eval JSON.
A greedy JSON extractor could return that instead of a real evaluation — these
tests pin the shape-validation that prevents it.
"""
import types

from app.agent import subagents


class _Echo:
    """Fake LLM returning a fixed text blob (like the prod mock echoing the prompt)."""

    def __init__(self, text: str):
        self._text = text

    def complete(self, messages, tools=None):
        return types.SimpleNamespace(text=self._text)


def test_evaluator_falls_back_on_non_evaluation_json(monkeypatch):
    monkeypatch.setattr(subagents, "LLMClient", lambda: _Echo('echo Profile {"targets": {}} end'))
    ev = subagents.evaluator("job md", {"targets": {}})
    assert ev.get("fit_score") is not None  # deterministic fallback, not the echoed profile


def test_evaluator_accepts_a_real_evaluation(monkeypatch):
    monkeypatch.setattr(subagents, "LLMClient", lambda: _Echo('{"fit_score": 0.9, "strengths": ["x"]}'))
    assert subagents.evaluator("job md", {})["fit_score"] == 0.9


def test_upskiller_falls_back_on_non_gap_json(monkeypatch):
    monkeypatch.setattr(subagents, "LLMClient", lambda: _Echo('noise {"foo": 1} noise'))
    assert "missing_skills" in subagents.upskiller("job md", {"x": 1})


def test_reviewer_keeps_evaluation_when_revision_is_garbage(monkeypatch):
    monkeypatch.setattr(subagents, "LLMClient", lambda: _Echo('not json {"targets": {}}'))
    evaluation = {"fit_score": 0.5, "strengths": [], "weaknesses": [], "materials": []}
    assert subagents.reviewer(evaluation, "job md")["fit_score"] == 0.5
