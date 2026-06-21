"""Synthetic demo personas + a seeder, for PEREGRINE_DATASET=<persona> mode.

Every person, company, school and project below is **fictional** — invented to
feel real (plausible names, comp, timelines) but matching no actual entity — so
the dataset is safe to commit and ship. Selecting a persona via the
PEREGRINE_DATASET env var seeds an isolated, gitignored runtime dataset on boot
(see config.ensure_dirs), leaving any real user data untouched. Used for live
demos, exercising new features, and CI.

Each persona = a profile + a few field-appropriate jobs. Some jobs carry a saved
`evaluation` (fit) and `upskilling` (skill-gap) result, and some are `applied`,
so the Jobs pipeline, Applications, Upskilling and Insights views all populate.
"""
from __future__ import annotations

from typing import Any


def _skill(name: str, level: str, evidence: str) -> dict[str, str]:
    return {"name": name, "level": level, "evidence": evidence}


# --------------------------------------------------------------------------- #
# Personas
# --------------------------------------------------------------------------- #
PERSONAS: dict[str, dict[str, Any]] = {
    "ai-engineer": {
        "profile": {
            "name": "Maya Lindqvist",
            "headline": "Machine Learning Engineer",
            "location": "Toronto, ON",
            "open_to_relocation": True,
            "work_auth": ["Canadian Citizen"],
            "needs_sponsorship": False,
            "comp": {"currency": "CAD", "base_min": 140000, "base_target": 175000},
            "preferences": {
                "roles": ["Machine Learning Engineer", "Applied Scientist", "ML Platform Engineer"],
                "industries": ["AI", "Healthcare AI"],
                "flexibility": "hybrid",
                "avoid": ["on-call heavy", "pure research"],
            },
            "skills": [
                _skill("Python", "expert", "5 yrs; built the 'Helios' recommender at Northwind"),
                _skill("PyTorch", "advanced", "trained vision and LLM models in production"),
                _skill("LLM fine-tuning", "advanced", "LoRA/QLoRA on Llama-class models"),
                _skill("Distributed training", "intermediate", "Ray + DeepSpeed on 8-GPU nodes"),
                _skill("MLOps / Kubernetes", "intermediate", "Kubeflow pipelines, model registry"),
                _skill("RAG systems", "advanced", "built the 'Helix' retrieval stack"),
            ],
            "targets": {
                "roles": ["Machine Learning Engineer", "Applied Scientist"],
                "locations": ["Toronto", "Remote"],
                "work_mode": "hybrid",
                "min_salary": 140000,
                "include_keywords": ["LLM", "PyTorch", "RAG"],
                "exclude_keywords": ["unpaid", "security clearance"],
            },
            "resume_path": "resume/maya_lindqvist.pdf",
        },
        "jobs": [
            {
                "company": "Luma AI", "company_job_id": "LUMA-ML-204",
                "position": "Machine Learning Engineer, LLM Platform",
                "location": "Toronto, ON", "flexibility": "hybrid",
                "salary_min": 150000, "salary_max": 190000, "currency": "CAD",
                "posted_date": "2026-06-12", "role_category": "Engineering", "starred": True,
                "url": "https://example.com/luma/ml-204",
                "description": "Own the fine-tuning and serving stack for Luma's customer-facing LLM "
                               "assistants. You'll ship retrieval-augmented features end to end and "
                               "partner with research to productionize new models.",
                "evaluation": {
                    "fit_score": 0.84, "recommendation": "apply",
                    "strengths": ["Direct LLM fine-tuning + RAG experience", "Production PyTorch serving",
                                  "Comp and hybrid location align"],
                    "weaknesses": ["Less depth on multi-region serving", "No prior fintech domain"],
                    "materials": ["Tailor resume around the Helix RAG project", "Prep a serving-latency story"],
                },
                "upskilling": {
                    "summary": "Strong match; close two infra gaps to be a clear top candidate.",
                    "missing_skills": [
                        {"skill": "Multi-region model serving", "why": "Role lists global low-latency serving",
                         "how_to_close": "Build a small Triton + load-balancer demo across two regions"},
                        {"skill": "Token-cost observability", "why": "They emphasize cost-aware inference",
                         "how_to_close": "Add per-request token/cost dashboards to a side project"},
                    ],
                },
            },
            {
                "company": "Northwind Robotics", "company_job_id": "NWR-APS-77",
                "position": "Applied Scientist, Perception",
                "location": "Waterloo, ON", "flexibility": "onsite",
                "salary_min": 160000, "salary_max": 200000, "currency": "CAD",
                "posted_date": "2026-06-05", "role_category": "Research", "status": "applied",
                "applied_date": "2026-06-09", "url": "https://example.com/northwind/aps-77",
                "description": "Develop perception models for autonomous mobile robots: detection, "
                               "tracking, and sensor fusion. Ship models to embedded targets.",
                "notes": "Referred by a former teammate; recruiter call scheduled.",
            },
            {
                "company": "Cobalt Analytics", "company_job_id": "COB-MLP-12",
                "position": "ML Platform Engineer",
                "location": "Remote (Canada)", "flexibility": "remote",
                "salary_min": 145000, "salary_max": 180000, "currency": "CAD",
                "posted_date": "2026-06-18", "role_category": "Engineering",
                "url": "https://example.com/cobalt/mlp-12",
                "description": "Build the internal ML platform — feature store, training orchestration, "
                               "and CI for models — used by a dozen data scientists.",
            },
        ],
    },
    "ux-designer": {
        "profile": {
            "name": "Diego Marchetti",
            "headline": "Senior Product Designer",
            "location": "Lisbon, Portugal",
            "open_to_relocation": False,
            "work_auth": ["EU work permit"],
            "needs_sponsorship": False,
            "comp": {"currency": "EUR", "base_min": 55000, "base_target": 70000},
            "preferences": {
                "roles": ["Product Designer", "UX Designer", "Design Systems Lead"],
                "industries": ["SaaS", "Health"],
                "flexibility": "remote",
                "avoid": ["agency churn", "no research budget"],
            },
            "skills": [
                _skill("Figma", "expert", "daily driver; ran 40+ component libraries"),
                _skill("Design systems", "advanced", "built and shipped the 'Atlas' design system"),
                _skill("User research", "advanced", "moderated + unmoderated studies, 100+ sessions"),
                _skill("Prototyping", "expert", "high-fidelity interactive flows"),
                _skill("Accessibility (WCAG)", "intermediate", "audited and remediated to AA"),
                _skill("Webflow", "intermediate", "marketing-site builds"),
            ],
            "targets": {
                "roles": ["Senior Product Designer", "Design Systems Lead"],
                "locations": ["Remote", "Lisbon"],
                "work_mode": "remote",
                "min_salary": 55000,
                "include_keywords": ["design system", "research"],
                "exclude_keywords": ["pixel-pushing", "agency"],
            },
            "resume_path": "resume/diego_marchetti.pdf",
        },
        "jobs": [
            {
                "company": "Verde Studio", "company_job_id": "VRD-PD-9",
                "position": "Senior Product Designer",
                "location": "Remote (EU)", "flexibility": "remote",
                "salary_min": 58000, "salary_max": 72000, "currency": "EUR",
                "posted_date": "2026-06-14", "role_category": "Design", "starred": True,
                "url": "https://example.com/verde/pd-9",
                "description": "Lead end-to-end design for Verde's analytics product — from research "
                               "through shipped UI — and grow the shared component library.",
                "evaluation": {
                    "fit_score": 0.79, "recommendation": "apply",
                    "strengths": ["Design-systems leadership ('Atlas')", "Strong research practice",
                                  "Remote-EU and comp fit"],
                    "weaknesses": ["Light on data-viz patterns", "No prior B2B analytics domain"],
                    "materials": ["Lead the portfolio with the Atlas case study", "Add a data-viz redesign sample"],
                },
                "upskilling": {
                    "summary": "Great fit; sharpen data-visualization depth.",
                    "missing_skills": [
                        {"skill": "Data-visualization patterns", "why": "Product is analytics-heavy",
                         "how_to_close": "Redesign a dashboard and document the chart-choice rationale"},
                        {"skill": "Design tokens at scale", "why": "They want a maintainable token system",
                         "how_to_close": "Publish a token pipeline (Figma vars -> code) write-up"},
                    ],
                },
            },
            {
                "company": "Brightside Health", "company_job_id": "BSH-UX-31",
                "position": "UX Designer",
                "location": "Lisbon, Portugal", "flexibility": "hybrid",
                "salary_min": 48000, "salary_max": 60000, "currency": "EUR",
                "posted_date": "2026-06-04", "role_category": "Design", "status": "applied",
                "applied_date": "2026-06-08", "url": "https://example.com/brightside/ux-31",
                "description": "Design calm, accessible patient-facing flows for a telehealth app.",
                "notes": "Take-home prompt submitted; awaiting review.",
            },
            {
                "company": "Tangram", "company_job_id": "TGM-DSL-3",
                "position": "Design Systems Lead",
                "location": "Remote (EU)", "flexibility": "remote",
                "salary_min": 62000, "salary_max": 78000, "currency": "EUR",
                "posted_date": "2026-06-19", "role_category": "Design",
                "url": "https://example.com/tangram/dsl-3",
                "description": "Own the design system across four product squads; set contribution "
                               "guidelines and governance.",
            },
        ],
    },
    "chem-phd": {
        "profile": {
            "name": "Dr. Priya Raman",
            "headline": "Synthetic Organic Chemist (PhD)",
            "location": "Manchester, UK",
            "open_to_relocation": True,
            "work_auth": ["UK work permit"],
            "needs_sponsorship": False,
            "comp": {"currency": "GBP", "base_min": 42000, "base_target": 52000},
            "preferences": {
                "roles": ["Process Chemist", "R&D Scientist", "Medicinal Chemist"],
                "industries": ["Pharma", "Specialty chemicals"],
                "flexibility": "onsite",
                "avoid": ["sales", "pure QC"],
            },
            "skills": [
                _skill("Organic synthesis", "expert", "PhD at the Riverton Institute of Technology"),
                _skill("NMR & mass spectrometry", "advanced", "structure elucidation, daily use"),
                _skill("Medicinal chemistry", "advanced", "SAR campaigns on 3 lead series"),
                _skill("HPLC purification", "advanced", "prep + analytical method development"),
                _skill("Process optimization", "intermediate", "scaled two routes from mg to 100 g"),
                _skill("Python (cheminformatics)", "beginner", "RDKit scripting for analogue triage"),
            ],
            "targets": {
                "roles": ["Process Chemist", "Medicinal Chemist"],
                "locations": ["Manchester", "Cambridge", "Leeds"],
                "work_mode": "onsite",
                "min_salary": 42000,
                "include_keywords": ["synthesis", "scale-up", "medicinal"],
                "exclude_keywords": ["sales", "field"],
            },
            "resume_path": "resume/priya_raman_cv.pdf",
        },
        "jobs": [
            {
                "company": "Cobalt Therapeutics", "company_job_id": "CBT-PC-5",
                "position": "Process Chemist",
                "location": "Manchester, UK", "flexibility": "onsite",
                "salary_min": 45000, "salary_max": 55000, "currency": "GBP",
                "posted_date": "2026-06-11", "role_category": "Science", "starred": True,
                "url": "https://example.com/cobalt-tx/pc-5",
                "description": "Develop and optimize scalable synthetic routes for clinical candidates; "
                               "own route selection, safety, and tech-transfer to manufacturing.",
                "evaluation": {
                    "fit_score": 0.81, "recommendation": "apply",
                    "strengths": ["Hands-on route scale-up (mg->100g)", "Strong synthesis + purification",
                                  "Local to Manchester"],
                    "weaknesses": ["Limited GMP documentation exposure", "No DoE statistics background"],
                    "materials": ["Highlight the two scaled routes", "Prep a tech-transfer example"],
                },
                "upskilling": {
                    "summary": "Strong technical fit; add regulated-process fluency.",
                    "missing_skills": [
                        {"skill": "GMP documentation", "why": "Clinical scale-up is GMP-regulated",
                         "how_to_close": "Complete a short GMP/quality-systems course and note it"},
                        {"skill": "Design of Experiments (DoE)", "why": "They optimize via DoE",
                         "how_to_close": "Run a DoE on a model reaction (JMP/Minitab) and write it up"},
                    ],
                },
            },
            {
                "company": "Helios Pharma", "company_job_id": "HLP-RD-22",
                "position": "R&D Scientist, Medicinal Chemistry",
                "location": "Cambridge, UK", "flexibility": "onsite",
                "salary_min": 48000, "salary_max": 58000, "currency": "GBP",
                "posted_date": "2026-06-03", "role_category": "Science", "status": "applied",
                "applied_date": "2026-06-07", "url": "https://example.com/helios/rd-22",
                "description": "Design and synthesize novel analogues in a CNS lead-optimization program.",
                "notes": "Application in; hiring manager viewed LinkedIn.",
            },
            {
                "company": "Greenfield Materials", "company_job_id": "GFM-FC-8",
                "position": "Formulation Chemist",
                "location": "Leeds, UK", "flexibility": "onsite",
                "salary_min": 40000, "salary_max": 50000, "currency": "GBP",
                "posted_date": "2026-06-17", "role_category": "Science",
                "url": "https://example.com/greenfield/fc-8",
                "description": "Formulate specialty coatings; balance performance, cost, and stability.",
            },
        ],
    },
    "bio-scientist": {
        "profile": {
            "name": "Dr. Sam Okonkwo",
            "headline": "Computational Biologist",
            "location": "Boston, MA",
            "open_to_relocation": False,
            "work_auth": ["US Permanent Resident"],
            "needs_sponsorship": False,
            "comp": {"currency": "USD", "base_min": 110000, "base_target": 135000},
            "preferences": {
                "roles": ["Research Scientist", "Computational Biologist", "Bioinformatics Scientist"],
                "industries": ["Biotech", "Genomics"],
                "flexibility": "hybrid",
                "avoid": ["wet-lab only", "no compute budget"],
            },
            "skills": [
                _skill("Molecular biology", "expert", "PhD at Lakeside University"),
                _skill("CRISPR / Cas9", "advanced", "designed and validated knockout screens"),
                _skill("Bioinformatics (Python/R)", "advanced", "pipelines for bulk + single-cell data"),
                _skill("Genomics & scRNA-seq", "advanced", "analyzed 200k-cell atlases"),
                _skill("Statistics", "intermediate", "GLMs, multiple-testing correction"),
                _skill("Nextflow pipelines", "intermediate", "reproducible, containerized workflows"),
            ],
            "targets": {
                "roles": ["Computational Biologist", "Research Scientist"],
                "locations": ["Boston", "Cambridge MA", "Remote"],
                "work_mode": "hybrid",
                "min_salary": 110000,
                "include_keywords": ["single-cell", "genomics", "CRISPR"],
                "exclude_keywords": ["wet-lab only"],
            },
            "resume_path": "resume/sam_okonkwo_cv.pdf",
        },
        "jobs": [
            {
                "company": "Verdant Biosciences", "company_job_id": "VBS-RS-14",
                "position": "Research Scientist, Genomics",
                "location": "Boston, MA", "flexibility": "hybrid",
                "salary_min": 115000, "salary_max": 145000, "currency": "USD",
                "posted_date": "2026-06-13", "role_category": "Science", "starred": True,
                "url": "https://example.com/verdant/rs-14",
                "description": "Lead single-cell genomics analysis for target discovery; build "
                               "reproducible pipelines and partner with wet-lab teams.",
                "evaluation": {
                    "fit_score": 0.83, "recommendation": "apply",
                    "strengths": ["Deep scRNA-seq experience", "Reproducible Nextflow pipelines",
                                  "Local, hybrid, comp aligns"],
                    "weaknesses": ["Less cloud (AWS) infra depth", "No prior target-discovery domain"],
                    "materials": ["Lead with the 200k-cell atlas project", "Prep a pipeline-reproducibility story"],
                },
                "upskilling": {
                    "summary": "Excellent fit; add cloud-scale and discovery context.",
                    "missing_skills": [
                        {"skill": "AWS for genomics (Batch/S3)", "why": "Pipelines run on AWS",
                         "how_to_close": "Port a Nextflow pipeline to AWS Batch and document cost/runtime"},
                        {"skill": "Target-discovery workflows", "why": "Role centers on target ID",
                         "how_to_close": "Read 2 recent target-discovery papers; note the analysis stack"},
                    ],
                },
            },
            {
                "company": "Helix Therapeutics", "company_job_id": "HXT-CB-6",
                "position": "Computational Biologist",
                "location": "Cambridge, MA", "flexibility": "hybrid",
                "salary_min": 120000, "salary_max": 150000, "currency": "USD",
                "posted_date": "2026-06-02", "role_category": "Science", "status": "applied",
                "applied_date": "2026-06-06", "url": "https://example.com/helix-tx/cb-6",
                "description": "Analyze multi-omics data to nominate and validate therapeutic targets.",
                "notes": "Submitted; first-round screen next week.",
            },
            {
                "company": "Northpoint Labs", "company_job_id": "NPL-BIS-19",
                "position": "Bioinformatics Scientist",
                "location": "Remote (US)", "flexibility": "remote",
                "salary_min": 112000, "salary_max": 138000, "currency": "USD",
                "posted_date": "2026-06-16", "role_category": "Science",
                "url": "https://example.com/northpoint/bis-19",
                "description": "Build and maintain bioinformatics pipelines for a diagnostics platform.",
            },
        ],
    },
    "law-student": {
        "profile": {
            "name": "Hana Sato",
            "headline": "JD Candidate (Class of 2027)",
            "location": "Chicago, IL",
            "open_to_relocation": True,
            "work_auth": ["US Citizen"],
            "needs_sponsorship": False,
            "comp": {"currency": "USD", "base_min": 0, "base_target": 0},
            "preferences": {
                "roles": ["Summer Associate", "Legal Intern", "Judicial Clerk"],
                "industries": ["Corporate law", "Compliance"],
                "flexibility": "onsite",
                "avoid": ["unpaid", "solo practice"],
            },
            "skills": [
                _skill("Legal research (Westlaw/Lexis)", "advanced", "Auden Law Review staffer"),
                _skill("Legal writing", "advanced", "published a Law Review note"),
                _skill("Case analysis", "advanced", "moot court quarterfinalist"),
                _skill("Contract drafting", "intermediate", "transactional clinic"),
                _skill("Negotiation", "intermediate", "won the 2L negotiation competition"),
                _skill("Compliance", "beginner", "summer compliance-clinic project"),
            ],
            "targets": {
                "roles": ["Summer Associate", "Legal Intern"],
                "locations": ["Chicago", "Remote"],
                "work_mode": "onsite",
                "min_salary": 0,
                "include_keywords": ["corporate", "transactional", "compliance"],
                "exclude_keywords": ["unpaid"],
            },
            "resume_path": "resume/hana_sato_resume.pdf",
        },
        "jobs": [
            {
                "company": "Atlas Legal LLP", "company_job_id": "ATL-SA-2L",
                "position": "Summer Associate (Corporate)",
                "location": "Chicago, IL", "flexibility": "onsite",
                "posted_date": "2026-06-12", "role_category": "Legal", "starred": True,
                "url": "https://example.com/atlas-legal/sa-2l",
                "description": "2L summer associate rotating through M&A and capital markets; real "
                               "deal exposure, drafting, and diligence with a dedicated mentor.",
                "evaluation": {
                    "fit_score": 0.76, "recommendation": "apply",
                    "strengths": ["Law Review + strong writing", "Transactional clinic experience",
                                  "Based in Chicago"],
                    "weaknesses": ["No prior big-firm summer", "Limited securities-reg coursework"],
                    "materials": ["Polish the writing sample (transactional)", "Prep deal-vocabulary talking points"],
                },
                "upskilling": {
                    "summary": "Competitive; shore up securities/deal fundamentals.",
                    "missing_skills": [
                        {"skill": "Securities regulation basics", "why": "Capital-markets rotation assumes it",
                         "how_to_close": "Take the securities-reg elective or a CLE primer"},
                        {"skill": "Deal-process fluency", "why": "Diligence/closing mechanics are daily work",
                         "how_to_close": "Walk through a public M&A timeline and term sheet"},
                    ],
                },
            },
            {
                "company": "Meridian & Cole LLP", "company_job_id": "MC-INT-7",
                "position": "Legal Intern",
                "location": "Chicago, IL", "flexibility": "hybrid",
                "posted_date": "2026-06-05", "role_category": "Legal", "status": "applied",
                "applied_date": "2026-06-10", "url": "https://example.com/meridian-cole/int-7",
                "description": "Support the litigation team with research, memos, and filing prep.",
                "notes": "Applied via career services; writing sample sent.",
            },
            {
                "company": "Brightline Compliance", "company_job_id": "BLC-CLK-2",
                "position": "Legal Clerk (Compliance)",
                "location": "Remote (US)", "flexibility": "remote",
                "posted_date": "2026-06-18", "role_category": "Legal",
                "url": "https://example.com/brightline/clk-2",
                "description": "Assist a compliance team with policy research and regulatory tracking.",
            },
        ],
    },
}


def list_personas() -> list[str]:
    return sorted(PERSONAS)


# --------------------------------------------------------------------------- #
# Seeder
# --------------------------------------------------------------------------- #
def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- (none)"


def _job_md(spec: dict[str, Any], evaluation: dict[str, Any] | None) -> str:
    md = f"# {spec['position']} — {spec['company']}\n\n{spec.get('description', '').strip()}\n"
    if evaluation:
        md += (
            "\n## Fit evaluation\n\n"
            f"- **fit_score:** {evaluation['fit_score']}\n"
            f"- **recommendation:** {evaluation.get('recommendation', 'hold')}\n\n"
            f"### Strengths\n{_bullets(evaluation.get('strengths', []))}\n\n"
            f"### Weaknesses / gaps\n{_bullets(evaluation.get('weaknesses', []))}\n\n"
            f"### Materials to prepare\n{_bullets(evaluation.get('materials', []))}\n"
        )
    return md


def seed(dataset: str) -> None:
    """Write the chosen persona's profile, jobs, per-job markdown, saved
    upskilling results, and applications into the active (demo) data dirs.

    Uses the canonical data_store writers so the files match exactly what the app
    reads. Imported lazily by config.ensure_dirs to avoid an import cycle.
    """
    persona = PERSONAS[dataset]
    from . import data_store as store
    from .schemas import Application, Job

    store.write_profile(persona["profile"])

    for i, spec in enumerate(persona["jobs"], start=1):
        jid = f"2026-{i:03d}"
        evaluation = spec.get("evaluation")
        job = Job(
            id=jid,
            company=spec["company"],
            company_job_id=spec.get("company_job_id", f"req-{i:03d}"),
            position=spec["position"],
            status=spec.get("status", "open"),
            location=spec.get("location", ""),
            flexibility=spec.get("flexibility", ""),
            salary_min=spec.get("salary_min"),
            salary_max=spec.get("salary_max"),
            currency=spec.get("currency", "USD"),
            posted_date=spec.get("posted_date", ""),
            url=spec.get("url", ""),
            fit_score=evaluation["fit_score"] if evaluation else None,
            detail_md=f"data/jobs/{jid}.md",
            role_category=spec.get("role_category", ""),
            starred=spec.get("starred", False),
        )
        store.upsert_job(job)
        store.write_job_md(jid, _job_md(spec, evaluation))

        if spec.get("upskilling"):
            store.write_upskilling(jid, spec["upskilling"])

        if spec.get("applied") or spec.get("status") in ("applied", "interviewing", "offer", "rejected"):
            store.upsert_application(
                Application(
                    **job.model_dump(),
                    applied_date=spec.get("applied_date", spec.get("posted_date", "")),
                    notes=spec.get("notes", ""),
                )
            )
