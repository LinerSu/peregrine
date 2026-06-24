"""Skill categorizer — names map to the expected group (first match wins, word-boundary safe)."""
import pytest

from app.skills import classify_skill, normalize_category


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Python", "Languages"),
        ("OCaml", "Languages"),
        ("Rocq", "Languages"),
        ("JavaScript", "Languages"),
        ("Go", "Languages"),
        ("React", "Frameworks & Libraries"),
        ("PyTorch", "Frameworks & Libraries"),
        ("Docker", "Tools"),
        ("Kubernetes", "Tools"),
        ("GitHub", "Tools"),
        ("Git", "Tools"),
        ("Compilers", "Domains"),
        ("UI/UX", "Domains"),
        ("3D Graphics", "Domains"),
        ("Machine Learning", "Domains"),
        ("Leadership", "Soft skills"),
        ("Underwater Basket Weaving", ""),  # unknown -> Other (empty)
    ],
)
def test_classify_skill(name, expected):
    assert classify_skill(name) == expected


def test_word_boundary_no_false_match():
    # "go" must not be caught inside "Django"; "ml" not inside "HTML".
    assert classify_skill("Django") == "Frameworks & Libraries"
    assert classify_skill("HTML") == "Languages"


def test_normalize_category_clamps_to_canonical():
    assert normalize_category("Soft Skills", "Leadership") == "Soft skills"   # case-folded
    assert normalize_category("Tools", "anything") == "Tools"                  # already canonical
    assert normalize_category("Bogus", "Python") == "Languages"               # invalid -> classify
    assert normalize_category("", "Docker") == "Tools"                         # blank -> classify
    assert normalize_category("Nonsense", "whatever") == ""                    # invalid + unknown
