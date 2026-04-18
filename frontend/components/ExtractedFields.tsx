import type { ClinicianIntake, Mutation, PathologyFindings } from "@/lib/types";

function field(label: string, value: unknown) {
  const display =
    value === null ||
    value === undefined ||
    value === "unknown" ||
    value === "" ? (
      <span className="text-ink-500">—</span>
    ) : (
      String(value)
    );
  return (
    <div className="flex justify-between gap-4 py-1 text-sm border-b border-ink-800/60 last:border-none">
      <span className="text-ink-400">{label}</span>
      <span className="text-ink-100 text-right">{display}</span>
    </div>
  );
}

export function ExtractedFields({
  pathology,
  intake,
  mutations,
  tStage,
}: {
  pathology: PathologyFindings;
  intake: ClinicianIntake;
  mutations: Mutation[];
  tStage: string;
}) {
  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-5">
      <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest mb-3">
        Extracted oncology data
      </h2>
      <div className="grid md:grid-cols-2 gap-x-8">
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-500 mb-1 mt-1">
            Pathology
          </div>
          {field("Subtype", pathology.melanoma_subtype)}
          {field(
            "Breslow",
            pathology.breslow_thickness_mm !== null
              ? `${pathology.breslow_thickness_mm} mm`
              : null,
          )}
          {field(
            "Ulceration",
            pathology.ulceration === null
              ? null
              : pathology.ulceration
                ? "Yes"
                : "No",
          )}
          {field("Mitoses/mm²", pathology.mitotic_rate_per_mm2)}
          {field("TILs", pathology.tils_present)}
          {field("PD-L1", pathology.pdl1_estimate)}
          {field(
            "LAG-3 IHC",
            pathology.lag3_ihc_percent !== null
              ? `${pathology.lag3_ihc_percent}%`
              : null,
          )}
          {field("Derived T-stage", tStage)}
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-500 mb-1 mt-1">
            Clinical intake
          </div>
          {field("AJCC stage", intake.ajcc_stage)}
          {field("Age", intake.age_years)}
          {field("ECOG", intake.ecog)}
          {field(
            "Measurable (RECIST)",
            intake.measurable_disease_recist === null
              ? null
              : intake.measurable_disease_recist
                ? "Yes"
                : "No",
          )}
          {field(
            "Prior systemic Rx",
            intake.prior_systemic_therapy === null
              ? null
              : intake.prior_systemic_therapy
                ? "Yes"
                : "No",
          )}
          {field(
            "Prior anti-PD-1",
            intake.prior_anti_pd1 === null
              ? null
              : intake.prior_anti_pd1
                ? "Yes"
                : "No",
          )}
          {field(
            "Life expectancy",
            intake.life_expectancy_months
              ? `${intake.life_expectancy_months} mo`
              : null,
          )}
        </div>
      </div>

      <div className="mt-4 border-t border-ink-800/60 pt-3">
        <div className="text-xs uppercase tracking-wider text-ink-500 mb-2">
          Mutations ({mutations.length})
        </div>
        {mutations.length === 0 ? (
          <p className="text-sm text-ink-500">None detected in the PDF.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {mutations.map((m, i) => (
              <span
                key={`${m.gene}-${m.position}-${i}`}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-teal-400/10 text-teal-300 font-mono text-xs"
              >
                <span className="text-ink-100">{m.gene}</span>
                {m.ref_aa}
                {m.position}
                {m.alt_aa}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
