"""Role classifier — specific titles map to the expected family (first match wins)."""
import pytest

from app.roles import classify_role


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Machine Learning Engineer", "ML Engineer"),
        ("Senior Software Engineer", "SDE"),
        ("Staff Backend Engineer", "SDE"),
        ("Technical Program Manager - Sensing", "Program Manager"),
        ("Engineering Manager", "Manager"),
        ("Director of Engineering", "Manager"),
        ("Applied Scientist II", "Applied Scientist"),
        ("Senior Product Manager", "Product Manager"),
        ("Data Scientist", "Data Scientist"),
        ("Data Engineer", "Data Engineer"),
        ("Product Designer", "Designer"),
        ("Business Analyst", "Analyst"),
        ("Chief of Staff", "Other"),
        ("", "Other"),
    ],
)
def test_classify_role(title, expected):
    assert classify_role(title) == expected
