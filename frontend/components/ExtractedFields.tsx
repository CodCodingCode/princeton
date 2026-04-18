import type {
  ClinicianIntake,
  EnrichedBiomarkers,
  Mutation,
  NCCNEvidenceMap,
  NCCNEvidenceNodeRef,
  PathologyFindings,
} from "@/lib/types";

function isEmpty(value: unknown): boolean {
  return (
    value === null || value === undefined || value === "unknown" || value === ""
  );
}

function MissingBadge({ blocking }: { blocking: NCCNEvidenceNodeRef[] }) {
  if (blocking.length === 0) {
    return <span className="text-ink-500">—</span>;
  }
  const labels = blocking.map((n) => n.node_title).join(" · ");
  return (
    <span
      className="text-amber-400/80 text-xs italic"
      title={blocking.map((n) => `${n.node_id} — ${n.node_title}`).join("\n")}
    >
      Missing — blocks {labels}
    </span>
  );
}

function Row({
  label,
  value,
  blocking,
}: {
  label: string;
  value: unknown;
  blocking?: NCCNEvidenceNodeRef[];
}) {
  const empty = isEmpty(value);
  return (
    <div className="flex justify-between gap-4 py-1 text-sm border-b border-ink-800/60 last:border-none">
      <span className="text-ink-400">{label}</span>
      <span className="text-ink-100 text-right">
        {empty ? <MissingBadge blocking={blocking ?? []} /> : String(value)}
      </span>
    </div>
  );
}

export function ExtractedFields({
  pathology,
  intake,
  enrichment,
  mutations,
  tStage,
  evidenceMap,
}: {
  pathology: PathologyFindings;
  intake: ClinicianIntake;
  enrichment: EnrichedBiomarkers | null;
  mutations: Mutation[];
  tStage: string;
  evidenceMap: NCCNEvidenceMap;
}) {
  const blocks = (field: string): NCCNEvidenceNodeRef[] =>
    evidenceMap[field] ?? [];

  return (
    <div className="rounded-xl border border-ink-800 bg-ink-900/40 p-5">
      <h2 className="text-sm font-semibold text-teal-400 uppercase tracking-widest mb-1">
        Extracted oncology data
      </h2>

      <div className="mt-4">
        <div className="text-xs uppercase tracking-wider text-teal-300/80 mb-1">
          NCCN evidence
        </div>
        <p className="text-xs text-ink-500 mb-2">
          Inputs the NCCN cutaneous melanoma walker reads at each decision node.
          Missing fields block the listed node.
        </p>
        <div className="grid md:grid-cols-2 gap-x-8">
          <div>
            <Row
              label="Subtype"
              value={pathology.melanoma_subtype}
              blocking={blocks("melanoma_subtype")}
            />
            <Row
              label="Breslow"
              value={
                pathology.breslow_thickness_mm !== null
                  ? `${pathology.breslow_thickness_mm} mm`
                  : null
              }
              blocking={blocks("breslow_thickness_mm")}
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
              blocking={blocks("ulceration")}
            />
            <Row
              label="Mitoses/mm²"
              value={pathology.mitotic_rate_per_mm2}
              blocking={blocks("mitotic_rate_per_mm2")}
            />
            <Row
              label="TILs"
              value={pathology.tils_present}
              blocking={blocks("tils_present")}
            />
          </div>
          <div>
            <Row
              label="PD-L1"
              value={pathology.pdl1_estimate}
              blocking={blocks("pdl1_estimate")}
            />
            <Row
              label="LAG-3 IHC"
              value={
                pathology.lag3_ihc_percent !== null
                  ? `${pathology.lag3_ihc_percent}%`
                  : null
              }
              blocking={blocks("lag3_ihc_percent")}
            />
            <Row
              label="TMB"
              value={
                enrichment?.tmb_mut_per_mb != null
                  ? `${enrichment.tmb_mut_per_mb.toFixed(1)} mut/Mb`
                  : null
              }
              blocking={blocks("tumor_mutational_burden")}
            />
            <Row
              label="Derived T-stage"
              value={tStage}
              blocking={blocks("t_stage")}
            />
            <Row
              label="Mutations"
              value={mutations.length > 0 ? `${mutations.length} found` : null}
              blocking={blocks("mutations")}
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
          Trial eligibility
        </div>
        <p className="text-xs text-ink-500 mb-2">
          Inputs the Regeneron trial matcher reads. Separate from NCCN — missing
          values here do not block the railway.
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
