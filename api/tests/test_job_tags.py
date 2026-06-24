"""Per-job tag extraction — required level / skills / domains from a posting (deterministic)."""
from app.job_tags import extract_domains, extract_level, extract_skills


def test_extract_level():
    assert extract_level("PhD in CS required") == "PhD"
    assert extract_level("Master's degree or equivalent") == "MS"
    assert extract_level("MS preferred") == "MS"
    assert extract_level("Bachelor's in Engineering") == "BS"
    assert extract_level("a PhD or MS, either works") == "PhD"  # highest wins
    assert extract_level("no degree mentioned") == ""


def test_extract_skills():
    out = extract_skills("You'll write OCaml and Rocq, with some Python and Docker.")
    for s in ("OCaml", "Rocq/Coq", "Python", "Docker"):
        assert s in out


def test_extract_skills_avoids_prose_false_positives():
    assert extract_skills("We value clear communication and a can-do attitude.") == []
    # "java" inside "javascript" must NOT yield the Java tag.
    js = extract_skills("Strong JavaScript and TypeScript skills")
    assert "JavaScript" in js and "TypeScript" in js and "Java" not in js


def test_extract_domains():
    out = extract_domains("Work on compilers and machine learning systems")
    assert "Compilers" in out and "Machine Learning" in out


def test_job_tag_kwargs_used_by_scan_and_ingest():
    # The shared helper both scan and the paste/URL ingest path call, so every tracked job is
    # tagged consistently (not just scanned ones).
    from app.agent.providers import RawPosting
    from app.agent.tools import _job_tag_kwargs

    kw = _job_tag_kwargs(
        RawPosting(company="X", company_job_id="1", position="Compiler Engineer",
                   description="PhD preferred. Strong OCaml and Rocq experience.")
    )
    assert kw["level"] == "PhD"
    assert "OCaml" in kw["req_skills"] and "Rocq/Coq" in kw["req_skills"]
    assert "Compilers" in kw["domains"]
    assert set(kw) == {"role_category", "level", "req_skills", "domains"}


def test_word_boundaries_no_false_positives():
    # word boundaries: "scalable"/"scale" ≠ Scala, "reactive" ≠ React, "MySQL" ≠ bare SQL,
    # "CV" (résumé) ≠ Computer Vision — but the real tokens still match.
    assert "Scala" not in extract_skills("build scalable systems that scale")
    assert "React" not in extract_skills("a reactive, proactive mindset")
    assert "SQL" not in extract_skills("experience with MySQL")
    assert "Computer Vision" not in extract_domains("please submit your CV / resume")
    assert "Scala" in extract_skills("strong Scala experience")
    assert "MySQL" in extract_skills("experience with MySQL")


def test_precision_misses_tightened():
    # "MS Office" must not read as a Master's; "spark joy" isn't Apache Spark;
    # "embedded in the team" isn't the Embedded domain.
    assert extract_level("Proficient in MS Office") == ""
    assert extract_level("MS in Computer Science") == "MS"  # real degree still detected
    assert "Spark" not in extract_skills("we want people who spark joy")
    assert "Spark" in extract_skills("experience with Apache Spark and PySpark")
    assert "Embedded" not in extract_domains("you'll be embedded in the product team")
    assert "Embedded" in extract_domains("embedded systems and firmware")
