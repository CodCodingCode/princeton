import type {
  ClinicianIntake,
  EnrichedBiomarkers,
  Mutation,
  PathologyFindings,
} from "@/lib/types";

function isEmpty(value: unknown): boolean {
  return (
    value === null || value === undefined || value === "unknown" || value === ""
  );
}

function Row({ label, value }: { label: string; value: unknown }) {
  const empty = isEmpty(value);
  return (
    <div className="flex justify-between gap-4 py-1 text-sm border-b border-ink-800/60 last:border-none">
      <span className="text-ink-400">{label}</span>
      <span className="text-ink-100 text-right">
        {empty ? <span className="text-ink-500">—</span> : String(value)}
      </span>
    </div>
  );
}

function prettyCancerType(t: string | null | undefined): string {
  if (!t || t === "unknown") return "—";
  return t.replace(/_/g, " ");
}

export function ExtractedFields({
  pathology,
  intake,
  enrichment,
  mutations,
  primaryCancerType,
  tStage,
}: {
  pathology: PathologyFindings;
  intake: ClinicianIntake;
  enrichment: EnrichedBiomarkers | null;
  mutations: Mutation[];
  primaryCancerType: string;
  tStage: string;
}) {
  const isMelanoma = primaryCancerType === "cutaneous_melanoma";

  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-5">
      <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest mb-1">
        Extracted oncology data
      </h2>

      <div className="mt-4">
        <div className="text-xs uppercase tracking-wider text-teal-300/80 mb-1">
          Diagnosis
        </div>
        <p className="text-xs text-ink-500 mb-2">
          Drives the dynamic railway and RAG retrieval from the phase-2+ trial
          corpus.
        </p>
        <div className="grid md:grid-cols-2 gap-x-8">
          <div>
            <Row
              label="Primary cancer"
              value={prettyCancerType(
                primaryCancerType || pathology.primary_cancer_type,
              )}
            />
            <Row label="Histology" value={pathology.histology} />
            <Row label="Primary site" value={pathology.primary_site} />
          </div>
          <div>
            <Row
              label="TMB"
              value={
                enrichment?.tmb_mut_per_mb != null
                  ? `${enrichment.tmb_mut_per_mb.toFixed(1)} mut/Mb`
                  : null
              }
            />
            <Row
              label="Mutations"
              value={mutations.length > 0 ? `${mutations.length} found` : null}
            />
          </div>
        </div>

        {mutations.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
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

      <div className="mt-6">
        <div className="text-xs uppercase tracking-wider text-ink-400 mb-1">
          Melanoma-specific pathology
        </div>
        <p className="text-xs text-ink-500 mb-2">
          {isMelanoma
            ? "Fields used by the melanoma NCCN framework."
            : "Populated only for melanoma cases — expect these to be empty for other tumor types."}
        </p>
        <div className="grid md:grid-cols-2 gap-x-8">
          <div>
            <Row label="Subtype" value={pathology.melanoma_subtype} />
            <Row
              label="Breslow"
              value={
                pathology.breslow_thickness_mm !== null
                  ? `${pathology.breslow_thickness_mm} mm`
                  : null
              }
            />
            <Row
              label="Ulceration"
              value={
                pathology.ulceration === null
                  ? null
                  : pathology.ulceration
                    ? "Yes"
                    : "No"
              }
            />
            <Row label="Mitoses/mm²" value={pathology.mitotic_rate_per_mm2} />
            <Row label="TILs" value={pathology.tils_present} />
          </div>
          <div>
            <Row label="PD-L1" value={pathology.pdl1_estimate} />
            <Row
              label="LAG-3 IHC"
              value={
                pathology.lag3_ihc_percent !== null
                  ? `${pathology.lag3_ihc_percent}%`
                  : null
              }
            />
            <Row label="Derived T-stage" value={tStage} />
          </div>
        </div>
      </div>

      <div className="mt-6">
        <div className="text-xs uppercase tracking-wider text-ink-400 mb-1">
          Trial eligibility
        </div>
        <p className="text-xs text-ink-500 mb-2">
          Inputs the Regeneron trial matcher reads. Separate from the railway —
          missing values here do not block phase-level recommendations.
        </p>
        <div className="grid md:grid-cols-2 gap-x-8">
          <div>
            <Row label="AJCC stage" value={intake.ajcc_stage} />
            <Row label="Age" value={intake.age_years} />
            <Row label="ECOG" value={intake.ecog} />
            <Row
              label="Measurable (RECIST)"
              value={
                intake.measurable_disease_recist === null
                  ? null
                  : intake.measurable_disease_recist
                    ? "Yes"
                    : "No"
              }
            />
          </div>
          <div>
            <Row
              label="Prior systemic Rx"
              value={
                intake.prior_systemic_therapy === null
                  ? null
                  : intake.prior_systemic_therapy
                    ? "Yes"
                    : "No"
              }
            />
            <Row
              label="Prior anti-PD-1"
              value={
                intake.prior_anti_pd1 === null
                  ? null
                  : intake.prior_anti_pd1
                    ? "Yes"
                    : "No"
              }
            />
            <Row
              label="Life expectancy"
              value={
                intake.life_expectancy_months
                  ? `${intake.life_expectancy_months} mo`
                  : null
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}
