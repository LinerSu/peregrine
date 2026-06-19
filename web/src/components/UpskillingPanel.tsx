// Upskilling tab placeholder. The skill exists under .agents/skills/; the
// backend tool + endpoint are still on the roadmap (see AGENTS.md).
export default function UpskillingPanel() {
  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-xl mx-auto text-center mt-10 space-y-3">
        <div className="text-3xl">📈</div>
        <h3 className="text-base font-semibold text-gray-700">Upskilling</h3>
        <p className="text-sm text-gray-500">
          Compares the skills a job wants against your profile, flags gaps, and suggests how to
          close them. The analysis tool isn't wired up yet — for now, ask the assistant{" "}
          <span className="italic">"what skills am I missing for &lt;job&gt;?"</span> and it will
          reason over the job's qualifications and your profile.
        </p>
      </div>
    </div>
  );
}
