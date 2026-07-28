// Copyable prompts for EXTERNAL agents (another Claude session, ChatGPT, …) that
// generate markdown Peregrine can take back in. The field lists mirror the backend
// schemas (api/app/schemas.py Job / Application) — api/tests/test_agent_prompts.py
// pins that this file never drifts from them. The never-invent rule is the same one
// the product itself lives by.

export const JOB_AGENT_PROMPT = `You are helping me capture a job posting for my personal job tracker. Produce ONE
markdown document describing the posting, in exactly this shape:

# <Position> — <Company>

- **company:** <company name>
- **position:** <exact job title>
- **company_job_id:** <the employer's requisition/job id, e.g. R-4521>
- **location:** <as posted; join multiple locations with " | ">
- **flexibility:** <remote | hybrid | onsite>
- **salary:** <min>–<max> <currency code, e.g. USD> (base or total, as stated)
- **posted_date:** <YYYY-MM-DD>
- **close_date:** <YYYY-MM-DD application deadline>
- **url:** <direct link to the posting>

## Posting
<the FULL posting text, lightly cleaned: what you'll do, basic qualifications,
preferred qualifications, restrictions (work authorization / citizenship /
clearance), compensation notes. Keep the ORIGINAL wording — my tracker derives
skill and degree tags from this text. Strip site navigation and boilerplate.>

Rules — follow strictly:
1. NEVER invent, infer, or estimate a value. If the posting does not state a
   field, leave it blank after the colon. No guessed salaries, no guessed dates.
2. Dates in ISO YYYY-MM-DD. Salary as plain numbers (300000, not "300k").
3. flexibility only if the posting explicitly states it.
4. Output ONLY the markdown document — no commentary before or after.
`;

export const APPLICATION_AGENT_PROMPT = `You are helping me record a job application I have ALREADY SUBMITTED, for my
personal tracker. Produce ONE markdown document in exactly this shape:

# Application — <Position> — <Company>

- **company:** <company name>
- **position:** <job title as applied>
- **company_job_id:** <requisition id, if known>
- **applied_date:** <YYYY-MM-DD I submitted it>
- **status:** <applied | interviewing | offer | rejected>
- **interview_date:** <YYYY-MM-DD, only if scheduled>
- **location:** <as posted>
- **salary:** <min>–<max> <currency code, as posted>
- **url:** <link to the posting>
- **contacts:** <name — role — profile link; separate multiple with ";">

## Notes
<anything worth remembering: referral used, portal confirmation number, which CV
version I sent, promised response window, follow-up plan>

## Posting (include if you have it)
<the full posting text — this lets my tracker link the application to a job>

Rules — follow strictly: never invent values (blank if unknown); ISO dates;
status from the exact vocabulary above; contacts only if I actually have them —
never scrape or guess people. Output ONLY the markdown.
`;
