import { useEffect, useState } from "react";
import { api, type Insights } from "../api";

// Pipeline analytics: a conversion funnel, fit-score distribution, and weekly
// activity — all rendered with plain Tailwind bars (no chart dependency).
export default function InsightsPanel() {
  const [data, setData] = useState<Insights | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let live = true;
    api
      .getStats()
      .then((d) => live && setData(d))
      .catch((e) => live && setErr((e as Error).message));
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
