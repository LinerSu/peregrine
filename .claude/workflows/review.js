export const meta = {
  name: 'review',
  description: 'Independent multi-agent pre-PR review: a reviewer per dimension (correctness, security, privacy/PII, tests, contract, regression), each finding adversarially verified, then synthesized into a READY / NEEDS-WORK verdict. Diff-scoped by default; pass {scope:"full"} for a whole-repo scan.',
  whenToUse: 'Run before opening a PR (or any time you want an independent review). Replaces the external reviewer.',
  phases: [
    { title: 'Review', detail: 'one independent reviewer per dimension' },
    { title: 'Verify', detail: 'adversarially verify each finding (refute by default)' },
    { title: 'Synthesize', detail: 'dedupe, rank, verdict' },
  ],
}

// args: { repo?: string, scope?: 'diff'|'full', base?: string }
const repo = (args && args.repo) || '.'
const scope = (args && args.scope) || 'diff'
const base = (args && args.base) || 'main'

const target =
  scope === 'full'
    ? 'the FULL codebase (concentrate on api/app/ and web/src/; skip vendored/generated dirs)'
    : `ONLY the pending change: run \`git -C ${repo} --no-pager diff ${base}...HEAD\` and \`git -C ${repo} --no-pager diff\` ` +
      `(staged+unstaged) and review any new/untracked files under api/ and web/. Do not review unrelated code.`

const DIMENSIONS = [
  { key: 'correctness', lens: 'logic bugs, wrong/edge-case behavior, error handling, data integrity, off-by-one, null/None, race conditions, CSV round-trip' },
  { key: 'security', lens: 'injection, XSS / unsafe href (javascript:/data:), unsafe eval/deserialization, path traversal, SSRF, auth gaps, secrets in code' },
  { key: 'privacy', lens: 'PII / personal-data leaks: any real CV/profile/job/application/contact data, real email addresses or names, or secrets added to SOURCE/TESTS/FIXTURES, or data written outside the gitignored personal-data paths (data/*.csv, config/profile.yml, resume/, applications/, .demo/). Synthetic @example.com fixtures are fine.' },
  { key: 'tests', lens: 'missing or weak coverage for the changed behavior; tests that assert nothing meaningful; a fix with no regression test' },
  { key: 'contract', lens: 'the Internal+External mode contract — every LLM-backed feature must work in BOTH modes (Internal = copyable command -> local Claude -> store-only PUT -> web polls); store-only endpoints must not call the LLM; no change that breaks one mode' },
  { key: 'regression', lens: 'behavior that could break existing features; API/schema/CSV backward-compat; a serve-time change that diverges from a scan-time gate' },
]

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          title: { type: 'string' },
          file: { type: 'string' },
          line: { type: 'string', description: 'line or range, e.g. "42" or "10-14"' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          detail: { type: 'string', description: 'what is wrong and why it matters' },
          fix: { type: 'string', description: 'concrete suggested fix' },
        },
        required: ['title', 'file', 'severity', 'detail', 'fix'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    real: { type: 'boolean', description: 'true ONLY if the issue genuinely holds after reading the actual code' },
    reason: { type: 'string' },
  },
  required: ['real', 'reason'],
}

log(`review: scope=${scope} base=${base} repo=${repo} — ${DIMENSIONS.length} dimensions`)

// Find -> verify, pipelined per dimension (a dimension's findings verify as soon as its review lands).
const reviewed = await pipeline(
  DIMENSIONS,
  (d) =>
    agent(
      `You are an INDEPENDENT, adversarial code reviewer — like an external third-party reviewer, not the author. ` +
        `Review ${target}. Repo root: ${repo}. Use Bash (git diff / git status) and Read to inspect the ACTUAL code. ` +
        `Lens for THIS pass: ${d.lens}. Report ONLY genuine, concrete, actionable issues (file + line + why + fix). ` +
        `Do not invent issues; if the change is clean on this lens, return an empty findings list.`,
      { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
    ),
  (review, d) =>
    parallel(
      (review && review.findings ? review.findings : []).map((f) => () =>
        agent(
          `Adversarially VERIFY this ${d.key} finding by reading the actual code in repo ${repo}. Try to REFUTE it. ` +
            `Set real=false if it's a false positive, already handled, out of scope for this change, or you're uncertain. ` +
            `Finding: ${JSON.stringify(f)}`,
          { label: `verify:${d.key}:${f.file}`, phase: 'Verify', schema: VERDICT_SCHEMA },
        ).then((v) => ({ ...f, dimension: d.key, verdict: v })),
      ),
    ),
)

const confirmed = reviewed
  .flat()
  .filter(Boolean)
  .filter((f) => f.verdict && f.verdict.real)

const order = { high: 0, medium: 1, low: 2 }
confirmed.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))

const summary = await agent(
  `Write a concise pre-PR review report from these VERIFIED findings (already adversarially confirmed): ` +
    `${JSON.stringify(confirmed)}. Group by severity (high → low), each as "file:line — title — fix". ` +
    `If there are zero findings, say the change is clean. End with a single line: "VERDICT: READY" if there are no ` +
    `high/medium findings, otherwise "VERDICT: NEEDS-WORK".`,
  { phase: 'Synthesize' },
)

return {
  scope,
  base,
  dimensions: DIMENSIONS.map((d) => d.key),
  confirmedCount: confirmed.length,
  high: confirmed.filter((f) => f.severity === 'high').length,
  medium: confirmed.filter((f) => f.severity === 'medium').length,
  low: confirmed.filter((f) => f.severity === 'low').length,
  findings: confirmed,
  report: summary,
}
