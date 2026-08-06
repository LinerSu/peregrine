"""Mechanical checks on a drafted letter.

These pin the countable half of the cover-letter rubric. Each test states the rule in the
form a reader would: not "the regex matches" but "this draft has the defect, and the check
says so". A rule with no failing example is a rule nobody has verified.
"""
import pytest

from app.letter_check import check_letter
from app.schemas import Job

JOB = Job(id="2026-001", company="Python Software Foundation", company_job_id="R1",
          position="Security Developer")

# A draft that passes every countable rule — the baseline the others deviate from.
GOOD = """Dear Members of the Python Security Response Team,

The mandate in this posting is capacity: driving reports to remediation and scaling
response ahead of demand. A small team scales through tooling, and the limit on security
tooling for C is not the availability of analyses but their precision. Making analysis
trustworthy enough that engineers act on its output is the problem addressed here, and it
is the constraint the Python Software Foundation describes in this posting.

The taint analysis traced untrusted input through struct fields and heap objects to the
places it can do damage in C programs, and it was evaluated on three widely used code
bases. The difficult part proved to be precision rather than detection: where a memory
model cannot distinguish two fields of one structure, marking either marks both, and every
site reading the unaffected field produces a warning. Analyses that report this way are
quickly disregarded. Extending the points-to layer so that one unpredictable array index
no longer discards field information reduced false security warnings by 6.6 to 13.2
percent at no measurable cost.

That work should continue on software that is depended upon rather than on benchmarks.
The Foundation runs OSS-Fuzz and the sanitizers already; measuring them by the proportion
of reports a maintainer acts upon, and reducing the remainder, is the same problem at a
different scale. Publishing those figures would make the value of the work legible to the
volunteers who sustain it.

Which stage of the current triage path consumes the most maintainer time would be the
first thing worth establishing, and the false-positive data from that pipeline is
available to share.

Yours sincerely,
"""


def _rules(text, job=JOB, unused=None):
    return {c["rule"] for c in check_letter(text, job, unused_evidence=unused)}


def test_a_clean_draft_reports_nothing():
    assert check_letter(GOOD, JOB) == []


def test_empty_letter_is_reported_rather_than_crashing():
    assert _rules("") == {"empty"}


@pytest.mark.parametrize("phrase", ["I would welcome the opportunity to discuss this role.",
                                    "I am excited to apply.",
                                    "I would be an ideal candidate."])
def test_cliches_any_applicant_could_have_written(phrase):
    assert "cliche" in _rules(GOOD.replace("Yours sincerely,", phrase + "\n\nYours sincerely,"))


def test_colloquialisms_are_flagged_for_a_formal_letter():
    assert "register" in _rules(GOOD.replace("Analyses that report this way", "Tools that cry wolf"))


def test_contractions_are_flagged():
    assert "register" in _rules(GOOD.replace("cannot distinguish", "can't distinguish"))


def test_a_letter_that_opens_every_sentence_with_i():
    drafted = """Dear Team,

I built a thing. I measured it. I improved it by 10 percent. I then wrote about it.

I would like to do more of that at the Python Software Foundation, where I would work on
the Python tooling that I have used for years and that I care about deeply.

Yours sincerely,
"""
    assert "i-openers" in _rules(drafted)


def test_an_employer_named_only_in_the_salutation_is_not_enough():
    # A letter that could be sent elsewhere with a find-and-replace is a stock letter.
    once = GOOD.replace("the Python Software Foundation describes in this posting",
                        "the organisation describes in this posting")
    once = once.replace("The Foundation runs OSS-Fuzz", "The team runs OSS-Fuzz")
    assert "employer" in _rules(once)


def test_a_letter_with_no_figure_anywhere():
    vague = GOOD.replace("by 6.6 to 13.2\npercent at no measurable cost",
                         "substantially at no measurable cost")
    vague = vague.replace("evaluated on three widely used code\nbases",
                          "evaluated on several widely used code bases")
    assert "specifics" in _rules(vague)


def test_length_is_reported_at_both_ends():
    assert "length" in _rules("Dear Team,\n\nShort letter about work.\n\nYours sincerely,\n")
    assert "length" in _rules(GOOD.replace("Yours sincerely,", GOOD * 2))


def test_selected_evidence_that_went_unused_is_named():
    checks = check_letter(GOOD, JOB, unused_evidence=["crab/taint/dfa.md — The problem"])
    assert any(c["rule"] == "evidence" and "crab/taint" in c["detail"] for c in checks)


def test_findings_are_ordered_worst_first():
    bad = GOOD.replace("Yours sincerely,", "I would welcome the opportunity to discuss.\n\nYours sincerely,")
    bad = bad.replace("cannot distinguish", "can't distinguish")
    severities = [c["severity"] for c in check_letter(bad, JOB)]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])


def test_possessives_are_not_contractions():
    """"the Foundation's scale" is formal English. Flagging it sends the writer to
    rephrase a correct sentence, which is worse than not checking at all."""
    ok = GOOD.replace("at the Foundation", "at the Foundation's own scale")
    assert "register" not in _rules(ok)
    assert "register" in _rules(GOOD.replace("cannot distinguish", "can't distinguish"))
    assert "register" in _rules(GOOD.replace("It is", "It's").replace("and it\nis the", "and it's the"))


def test_employer_counting_uses_a_word_that_identifies_the_company():
    """Two ways the naive version broke: an employer whose name starts with an article
    counted every "the" in the letter, and an unbounded match counted "Pythonic"."""
    from app.letter_check import _company_token

    assert _company_token("The Python Software Foundation") == "Foundation"
    assert _company_token("Acme Inc.") == "Acme"
    assert _company_token("The Co.") == ""          # nothing distinctive -> check is skipped

    the_job = Job(id="2026-001", company="The Foundation", company_job_id="R", position="Eng")
    # "the" appears constantly; only real mentions of Foundation should count
    thin = "Dear Team,\n\n" + ("The work in the posting is the thing. " * 12) + "\n\nYours sincerely,\n"
    assert "employer" in {c["rule"] for c in check_letter(thin, the_job)}

    py_job = Job(id="2026-001", company="Python Software Foundation", company_job_id="R", position="Eng")
    pythonic = GOOD.replace("the Python Software Foundation describes in this posting",
                            "Pythonic conventions describe this posting")
    pythonic = pythonic.replace("The Foundation runs OSS-Fuzz", "Pythonic tooling runs OSS-Fuzz")
    assert "employer" in {c["rule"] for c in check_letter(pythonic, py_job)}
