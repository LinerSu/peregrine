import { useEffect, useState } from "react";
import { api, type Insights, type Outcomes } from "../api";

// Pipeline analytics: a conversion funnel, fit-score distribution, weekly activity,
// plus outcome/rejection analytics (conversion rates, outcomes by fit-band & role,
// fit-score calibration, and stale-application follow-ups). Plain Tailwind bars.
export default function InsightsPanel() {
  const [data, setData] = useState<Insights | null>(null);
  const [outcomes, setOutcomes] = useState<Outcomes | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let live = true;
    // allSettled so an outcomes failure doesn't block the core funnel/distribution.
    Promise.allSettled([api.getStats(), api.getOutcomes()]).then(([s, o]) => {
      if (!live) return;
      if (s.status === "fulfilled") setData(s.value as Insights);
      else setErr((s.reason as Error).message);
      if (o.status === "fulfilled") setOutcomes(o.value as Outcomes);
    });
    return () => {
      live = false;
    };
  }, []);

  if (err) return <div className="p-6 text-sm text-rose-600">Couldn't load insights: {err}</div>;
  if (!data) return <div className="p-6 text-gray-400">Loading…</div>;

  const maxFunnel = Math.max(1, ...data.funnel.map((f) => f.count));
  const maxScore = Math.max(1, ...data.score_distribution.map((s) => s.count));
  const maxAct = Math.max(1, ...data.activity.flatMap((a) => [a.added, a.applied]));
  const section = "rounded-lg border border-gray-200 bg-white p-4";
  const heading = "text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3";
  const pct = (r: number) => `${Math.round(r * 100)}%`;
  const fit = (v: number | null) => (v == null ? "—" : v.toFixed(2));

  // A compact outcome row: label, applied count, an advance-rate bar, offer/rejected tallies.
  const outcomeRow = (label: string, g: Outcomes["by_fit_band"][number] | Outcomes["by_role"][number]) => (
    <div key={label} className="flex items-center gap-3 text-sm">
      <div className="w-40 truncate text-gray-600" title={label}>{label}</div>
      <div className="w-10 text-right text-gray-400">{g.applied}</div>
      <div className="flex-1 h-4 bg-gray-100 rounded" title={`${g.advanced}/${g.applied} advanced`}>
        <div
          className="h-4 rounded bg-indigo-500"
          style={{ width: `${g.advance_rate * 100}%`, minWidth: g.advanced ? "0.25rem" : 0 }}
        />
      </div>
      <div className="w-10 text-right text-xs text-gray-500">{pct(g.advance_rate)}</div>
      <div className="w-24 text-right text-xs text-gray-400">
        <span className="text-emerald-600">{g.offer}●</span> <span className="text-rose-500">{g.rejected}✕</span>
      </div>
    </div>
  );

  const hasOutcomeData =
    !!outcomes && (outcomes.conversion[0]?.d > 0 || outcomes.follow_ups.length > 0);

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Insights</h3>
          <p className="text-sm text-gray-500">
            {data.totals.jobs} jobs · {data.totals.evaluated} evaluated · {data.totals.applications} applications.
          </p>
        </div>

        {/* Funnel */}
        <section className={section}>
          <h4 className={heading}>Funnel</h4>
          <div className="space-y-2">
            {data.funnel.map((f) => (
              <div key={f.stage} className="flex items-center gap-3">
                <div className="w-24 text-sm text-gray-600">{f.stage}</div>
                <div className="flex-1 h-6 bg-gray-100 rounded">
                  <div
                    className="h-6 rounded bg-indigo-500 flex items-center justify-end px-2 text-xs text-white"
                    style={{ width: `${(f.count / maxFunnel) * 100}%`, minWidth: f.count ? "1.5rem" : 0 }}
                  >
                    {f.count || ""}
                  </div>
                </div>
                <div className="w-10 text-right text-xs text-gray-400">{Math.round(f.rate * 100)}%</div>
              </div>
            ))}
          </div>
        </section>

        {/* Outcome analytics */}
        {!hasOutcomeData ? (
          <section className={section}>
            <h4 className={heading}>Outcomes</h4>
            <p className="text-sm text-gray-400">
              No applications yet — conversion rates, rejection patterns, and follow-up reminders appear here once
              you've applied to a few jobs.
            </p>
          </section>
        ) : (
          <>
            {/* Conversion rates */}
            <section className={section}>
              <h4 className={heading}>Conversion</h4>
              <div className="space-y-2">
                {outcomes!.conversion.map((c) => (
                  <div key={c.label} className="flex items-center gap-3 text-sm">
                    <div className="w-40 text-gray-600">{c.label}</div>
                    <div className="flex-1 h-4 bg-gray-100 rounded">
                      <div
                        className="h-4 rounded bg-indigo-500"
                        style={{ width: `${c.rate * 100}%`, minWidth: c.n ? "0.25rem" : 0 }}
                      />
                    </div>
                    <div className="w-24 text-right text-xs text-gray-400">{c.n}/{c.d} · {pct(c.rate)}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* Calibration */}
            <section className={section}>
              <h4 className={heading}>Fit-score calibration</h4>
              <div className="flex flex-wrap gap-6 text-sm">
                <div>
                  <div className="text-gray-500">Advanced (interview/offer)</div>
                  <div className="text-lg font-semibold text-emerald-600">
                    {fit(outcomes!.calibration.advanced_avg_fit)}
                    <span className="ml-1 text-xs font-normal text-gray-400">avg fit · n={outcomes!.calibration.advanced_n}</span>
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Rejected</div>
                  <div className="text-lg font-semibold text-rose-500">
                    {fit(outcomes!.calibration.rejected_avg_fit)}
                    <span className="ml-1 text-xs font-normal text-gray-400">avg fit · n={outcomes!.calibration.rejected_n}</span>
                  </div>
                </div>
              </div>
              {outcomes!.calibration.advanced_avg_fit != null && outcomes!.calibration.rejected_avg_fit != null && (
                <p className="mt-2 text-xs text-gray-500">
                  {outcomes!.calibration.advanced_avg_fit > outcomes!.calibration.rejected_avg_fit
                    ? "Higher-fit jobs are advancing further — the score is tracking outcomes."
                    : "Fit score isn't separating outcomes yet — worth recalibrating what you apply to."}
                </p>
              )}
            </section>

            {/* Outcomes by fit band */}
            {outcomes!.by_fit_band.length > 0 && (
              <section className={section}>
                <h4 className={heading}>Outcomes by fit band</h4>
                <div className="space-y-2">{outcomes!.by_fit_band.map((g) => outcomeRow(g.band, g))}</div>
                <p className="mt-2 text-[10px] text-gray-400">applied · advance-rate bar · advance% · ●offers ✕rejections</p>
              </section>
            )}

            {/* Outcomes by role */}
            {outcomes!.by_role.length > 0 && (
              <section className={section}>
                <h4 className={heading}>Outcomes by role</h4>
                <div className="space-y-2">{outcomes!.by_role.slice(0, 8).map((g) => outcomeRow(g.role, g))}</div>
                {outcomes!.by_role.length > 8 && (
                  <p className="mt-2 text-[10px] text-gray-400">+{outcomes!.by_role.length - 8} more roles</p>
                )}
              </section>
            )}

            {/* Follow-ups */}
            <section className={section}>
              <h4 className={heading}>Follow-ups</h4>
              {outcomes!.follow_ups.length === 0 ? (
                <p className="text-sm text-gray-400">
                  No stale applications — nothing sitting in "applied" past {outcomes!.stale_days} days without an interview.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {outcomes!.follow_ups.map((f) => (
                    <li key={f.id} className="flex items-center gap-3 text-sm">
                      <span className="px-1.5 py-0.5 text-xs rounded-full bg-amber-100 text-amber-700">{f.days}d</span>
                      <span className="font-medium text-gray-700">{f.company}</span>
                      <span className="text-gray-500 truncate">{f.position}</span>
                      <span className="ml-auto text-xs text-gray-400">applied {f.applied_date}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        {/* Fit-score distribution */}
        <section className={section}>
          <h4 className={heading}>Fit-score distribution</h4>
          <div className="flex items-end gap-2 h-32">
            {data.score_distribution.map((s) => (
              <div key={s.range} className="flex-1 flex flex-col items-center justify-end h-full">
                <div className="text-xs text-gray-500">{s.count}</div>
                <div
                  className="w-full bg-emerald-400 rounded-t"
                  style={{ height: `${(s.count / maxScore) * 100}%`, minHeight: s.count ? "2px" : 0 }}
                />
                <div className="mt-1 text-[10px] text-gray-400">{s.range}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Weekly activity */}
        <section className={section}>
          <h4 className={heading}>Weekly activity</h4>
          {data.activity.length === 0 ? (
            <p className="text-sm text-gray-400">No dated activity yet.</p>
          ) : (
            <div className="flex items-end gap-2 overflow-x-auto pb-1">
              {data.activity.slice(-12).map((a) => (
                <div key={a.week} className="flex flex-col items-center justify-end min-w-[36px]">
                  <div className="flex items-end gap-0.5 h-24">
                    <div
                      className="w-3 bg-indigo-400 rounded-t"
                      title={`${a.added} added`}
                      style={{ height: `${(a.added / maxAct) * 100}%`, minHeight: a.added ? "2px" : 0 }}
                    />
                    <div
                      className="w-3 bg-amber-400 rounded-t"
                      title={`${a.applied} applied`}
                      style={{ height: `${(a.applied / maxAct) * 100}%`, minHeight: a.applied ? "2px" : 0 }}
                    />
                  </div>
                  <div className="mt-1 text-[10px] text-gray-400 whitespace-nowrap">{a.week.replace(/^\d+-/, "")}</div>
                </div>
              ))}
            </div>
          )}
          <div className="mt-2 flex gap-3 text-[10px] text-gray-500">
            <span className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-sm bg-indigo-400" /> added
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-sm bg-amber-400" /> applied
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
