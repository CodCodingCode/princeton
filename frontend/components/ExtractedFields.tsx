import type {
  ClinicianIntake,
  EnrichedBiomarkers,
  Mutation,
  PathologyFindings,
} from "@/lib/types";
import { formatStage } from "@/lib/plainEnglish";

// Shared formatters: keep presentation consistent with the PDF report so
// the downloaded document and the on-screen clinical tab use the same
// capitalization and the same human labels.
const UNKNOWN_TOKENS = new Set(["unknown", "", "none", "n/a", "na"]);

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (
    typeof value === "string" &&
    UNKNOWN_TOKENS.has(value.trim().toLowerCase())
  )
    return true;
  return false;
}

function prettyEnum(val: string | null | undefined): string | null {
  if (val == null) return null;
  const s = val.trim();
  if (!s || UNKNOWN_TOKENS.has(s.toLowerCase())) return null;
  const spaced = s.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function prettyCancerType(t: string | null | undefined): string | null {
  if (!t || UNKNOWN_TOKENS.has(t.toLowerCase())) return null;
  return prettyEnum(t);
}

function Row({ label, value }: { label: string; value: unknown }) {
  const empty = isEmpty(value);
  return (
    <div className="flex justify-between gap-4 py-1 text-sm border-b border-neutral-100 last:border-none">
      <span className="text-neutral-600">{label}</span>
      <span className="text-black text-right">
        {empty ? <span className="text-neutral-400">-</span> : String(value)}
      </span>
    </div>
  );
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
  // Pathology subsection only renders when at least one melanoma-shaped field
  // is populated. For non-melanoma cancers it would otherwise show a wall of
  // dashes, which reads as "broken" instead of "not applicable to this case".
  const hasMelanomaFields =
    pathology.melanoma_subtype !== "unknown" ||
    pathology.breslow_thickness_mm !== null ||
    pathology.ulceration !== null ||
    pathology.mitotic_rate_per_mm2 !== null ||
    (pathology.tils_present && pathology.tils_present !== "unknown") ||
    (pathology.pdl1_estimate && pathology.pdl1_estimate !== "unknown") ||
    pathology.lag3_ihc_percent !== null;

  return (
    <div className="card p-5">
      <h2 className="eyebrow mb-1">Oncology data summary</h2>

      <div className="mt-4">
        <div className="eyebrow mb-1">Diagnosis</div>
        <p className="text-xs text-neutral-500 mb-2">
          Core diagnostic fields that shape the treatment plan.
        </p>
        <div className="grid md:grid-cols-2 gap-x-8">
          <div>
            <Row
              label="Primary cancer"
              value={prettyCancerType(
                primaryCancerType || pathology.primary_cancer_type,
              )}
            />
            <Row label="Histology" value={prettyEnum(pathology.histology)} />
            <Row
              label="Primary site"
              value={prettyEnum(pathology.primary_site)}
            />
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
            {mutations.map((m, i) => {
              const isPoint =
                m.position !== null &&
                m.position !== undefined &&
                m.ref_aa &&
                m.alt_aa;
              return (
                <span
                  key={`${m.gene}-${m.position}-${m.raw_label ?? ""}-${i}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-700 font-mono text-xs"
                >
                  {isPoint ? (
                    <>
                      <span className="text-black">{m.gene}</span>
                      {m.ref_aa}
                      {m.position}
                      {m.alt_aa}
                    </>
                  ) : (
                    <span className="text-black">
                      {m.raw_label || m.gene || "(unknown variant)"}
                    </span>
                  )}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {hasMelanomaFields && (
        <div className="mt-6">
          <div className="eyebrow mb-1">Pathology details</div>
          <p className="text-xs text-neutral-500 mb-2">
            Tumor-specific findings for this case.
          </p>
          <div className="grid md:grid-cols-2 gap-x-8">
            <div>
              <Row
                label="Subtype"
                value={prettyEnum(pathology.melanoma_subtype)}
              />
              <Row
                label="Breslow thickness"
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
              <Row
                label="Mitoses per mm²"
                value={pathology.mitotic_rate_per_mm2}
              />
              <Row label="TILs" value={prettyEnum(pathology.tils_present)} />
            </div>
            <div>
              <Row label="PD-L1" value={prettyEnum(pathology.pdl1_estimate)} />
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
      )}

      <div className="mt-6">
        <div className="eyebrow mb-1">Trial eligibility</div>
        <p className="text-xs text-neutral-500 mb-2">
          Factors used to screen this case against open clinical trials. Missing
          values here do not block the phase-level recommendations.
        </p>
        <div className="grid md:grid-cols-2 gap-x-8">
          <div>
            <Row label="AJCC stage" value={formatStage(intake.ajcc_stage)} />
            <Row label="Age" value={intake.age_years} />
            <Row label="ECOG" value={intake.ecog} />
            <Row
              label="Measurable disease (RECIST)"
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
              label="Prior systemic therapy"
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
                  ? `${intake.life_expectancy_months} months`
                  : null
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}
