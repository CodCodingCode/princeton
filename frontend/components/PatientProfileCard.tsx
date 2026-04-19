"use client";

import type { PatientCase } from "@/lib/types";
import { formatStage } from "@/lib/plainEnglish";
import { Gauge } from "@/components/ui/Gauge";
import { TickRuler } from "@/components/ui/TickRuler";

// Physician-facing patient profile. Styled as a hospital EHR patient banner
// (identity strip on top — MRN, DOB, sex, race, language, contact) followed
// by dense clinical sections. Fields the intake pipeline doesn't capture
// render as "Not documented" rather than hiding, so the chart always looks
// like a real chart.

const UNKNOWN_TOKENS = new Set(["unknown", "", "none", "n/a", "na", "-"]);
const NOT_DOCUMENTED = "Not documented";

function isEmpty(v: unknown): boolean {
  if (v == null) return true;
  if (typeof v === "string" && UNKNOWN_TOKENS.has(v.trim().toLowerCase()))
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

function prettyBool(v: boolean | null): string | null {
  if (v === null) return null;
  return v ? "Yes" : "No";
}

// Deterministic MRN derived from case_id so repeated renders match. Takes
// the first 7 alphanumerics, uppercased — mimics an Epic/Cerner-style MRN.
function synthesizeMrn(caseId: string): string {
  const cleaned = caseId.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
  const short = cleaned.slice(0, 7) || "0000000";
  return short.padEnd(7, "0");
}

function cleanString(v: string | null | undefined): string | null {
  if (v == null) return null;
  const s = v.trim();
  if (!s || UNKNOWN_TOKENS.has(s.toLowerCase())) return null;
  return s;
}

// Normalize a patient name to "First Middle Last" order, regardless of how
// the registration form stored it. Handles:
//   "O'Brien, Margaret Anne"      → "Margaret Anne O'Brien"
//   "Margaret Anne O'Brien"        → "Margaret Anne O'Brien"
//   "Margaret A. O'Brien"          → "Margaret A. O'Brien"
//   "O'Brien, M."                  → "M. O'Brien"
function formatFullName(raw: string | null): string | null {
  if (!raw) return null;
  const s = raw.trim();
  if (!s) return null;
  if (s.includes(",")) {
    const [last, rest = ""] = s.split(",", 2);
    const firstMiddle = rest.trim().replace(/\s+/g, " ");
    const lastClean = last.trim();
    if (!firstMiddle) return lastClean;
    return `${firstMiddle} ${lastClean}`.replace(/\s+/g, " ").trim();
  }
  return s.replace(/\s+/g, " ").trim();
}

// Normalize sex to a consistent display form: "Male" / "Female" / whatever
// the form uses for non-binary options. Accepts "M"/"F" shorthand.
function formatSex(raw: string | null): string | null {
  const s = cleanString(raw);
  if (!s) return null;
  const lo = s.toLowerCase();
  if (lo === "m" || lo === "male") return "Male";
  if (lo === "f" || lo === "female") return "Female";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function joinMeta(parts: Array<string | null>): string | null {
  const clean = parts.filter((p): p is string => p != null && p.length > 0);
  return clean.length ? clean.join(" / ") : null;
}

// Two-letter initials from a full name. Handles "Last, First" and
// "First Last" forms. Falls back to "PT" when the name is missing.
function deriveInitials(name: string | null): string {
  if (!name) return "PT";
  const cleaned = name.replace(/[^A-Za-z,\s]/g, " ").trim();
  if (!cleaned) return "PT";
  if (cleaned.includes(",")) {
    const [last, rest = ""] = cleaned.split(",", 2);
    const first = rest.trim().split(/\s+/)[0] ?? "";
    return ((first[0] ?? "") + (last.trim()[0] ?? "")).toUpperCase() || "PT";
  }
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// Deterministic DOB from age_years. Uses a fixed pivot (July 1) so the
// banner is stable between renders rather than jittering each load.
function synthesizeDob(ageYears: number | null): string | null {
  if (ageYears == null) return null;
  const today = new Date();
  const year = today.getUTCFullYear() - ageYears;
  return `${year}-07-01`;
}

interface StatDef {
  label: string;
  value: string | null;
  mono?: boolean;
  wide?: boolean;
  // Plain-English caption shown under the value. Written for a lay reader —
  // explains what the field is and what this specific value tends to mean.
  hint?: string | null;
}

// Short layperson-friendly explanations for each clinical field the card
// surfaces. Returns null when we don't have a useful sentence — the hint
// row is then hidden.
function explainStat(label: string, value: string | null): string | null {
  if (!value) return null;
  const v = value.trim();
  const lower = v.toLowerCase();

  switch (label) {
    case "ECOG": {
      const n = parseInt(v.replace(/[^0-9]/g, ""), 10);
      if (Number.isNaN(n)) return null;
      const band = [
        "Fully active — no limits from the illness.",
        "Up and active, tires with strenuous work.",
        "Up more than half the day, can't work but self-care is fine.",
        "Mostly bed or chair, limited self-care.",
        "Bedbound — completely reliant on care.",
      ];
      return `Performance score (0–4). ${band[n] ?? ""}`.trim();
    }
    case "AJCC stage": {
      const s = v.toUpperCase();
      if (s.startsWith("1"))
        return "Early stage — tumor confined to where it started.";
      if (s.startsWith("2"))
        return "Larger or slightly deeper, still localized.";
      if (s.startsWith("3")) return "Spread to nearby lymph nodes or tissue.";
      if (s.startsWith("4")) return "Spread to distant organs (metastatic).";
      return "Overall stage combining tumor size, nodes, and spread.";
    }
    case "PD-L1":
      if (lower === "high")
        return "Tumor strongly displays the PD-L1 marker — often responds well to immunotherapy.";
      if (lower === "low")
        return "Tumor displays a little PD-L1 — immunotherapy may still help.";
      if (lower === "negative")
        return "Tumor doesn't display PD-L1 — immunotherapy response is less predictable.";
      return "A tumor marker that predicts how well immunotherapy may work.";
    case "TMB": {
      const n = parseFloat(v);
      if (Number.isNaN(n))
        return "Mutations per million DNA bases. Higher often means more immunotherapy benefit.";
      if (n >= 10)
        return "TMB-high (≥10). More mutations = more targets for the immune system.";
      return "TMB-low (<10). Fewer mutations for the immune system to flag.";
    }
    case "Breslow": {
      const n = parseFloat(v);
      if (Number.isNaN(n))
        return "How deep the melanoma has grown into the skin.";
      if (n < 1) return "Thin — grown less than 1 mm into the skin.";
      if (n < 2) return "Intermediate thickness (1–2 mm).";
      if (n < 4) return "Thick (2–4 mm) — deeper invasion.";
      return "Very thick (≥4 mm) — deeply invaded skin.";
    }
    case "Ulceration":
      return lower === "yes"
        ? "The skin over the tumor has broken down — a marker of more aggressive disease."
        : "The skin over the tumor is intact — a better prognostic sign.";
    case "Mitotic rate":
      return "How many tumor cells are actively dividing. Higher = faster-growing cancer.";
    case "TILs":
      if (lower.includes("brisk"))
        return "Immune cells are strongly attacking the tumor — a good sign.";
      if (lower.includes("non"))
        return "Some immune response, but not intense.";
      if (lower.includes("absent"))
        return "No immune cells infiltrating the tumor.";
      return "Whether the body's immune cells are attacking the tumor.";
    case "LAG-3 IHC":
      return "Another immune-checkpoint marker — relevant for LAG-3 blocking drugs like relatlimab or fianlimab.";
    case "UV signature":
      return "Fraction of mutations caused by sun/UV damage. High = classic sun-driven melanoma.";
    case "Subtype":
      if (lower.includes("nodular"))
        return "Nodular: a fast-growing vertical-growth melanoma.";
      if (lower.includes("superficial"))
        return "Superficial-spreading: the most common pattern, grows along the skin before going deeper.";
      if (lower.includes("lentigo"))
        return "Lentigo maligna: a slower, sun-damage-related melanoma, usually on the face.";
      if (lower.includes("acral"))
        return "Acral-lentiginous: appears on palms, soles, or under nails.";
      if (lower.includes("desmoplastic"))
        return "Desmoplastic: a rarer scar-like melanoma.";
      return null;
    case "Histology":
      return "The cancer's microscopic appearance — what kind of cells it's made of.";
    case "Primary site":
      return "Where in the body the cancer first started.";
    case "Laterality":
      return "Which side of the body the tumor is on.";
    case "Measurable (RECIST)":
      return lower === "yes"
        ? "There's a tumor big enough to measure on a scan — required for most drug trials."
        : "No scan-measurable tumor today — some trials won't apply without one.";
    case "Life expectancy":
      return "The care team's rough estimate — many trials require at least 3 months.";
    case "Prior systemic therapy":
      if (lower.startsWith("treatment-naive"))
        return "Patient has not received any prior cancer drugs.";
      if (lower.startsWith("yes"))
        return "Patient has received cancer drugs before — affects which trials they can join.";
      return null;
    case "Prior anti-PD-1":
      return lower === "yes"
        ? "Already received immunotherapy — changes which drugs are options next."
        : "No prior immunotherapy — first-line immunotherapy is still on the table.";
    case "Driver mutations":
      return "The DNA changes driving this cancer. Many have matching targeted drugs.";
    case "Extraction confidence":
      return "How confident the system is in the values it pulled from the records.";
    default:
      return null;
  }
}

// Grid section used for every clinical block. Values render as "Not
// documented" when empty so the chart stays visually uniform. When the
// stat's value is present and ``explainStat`` (or an explicit ``hint``)
// returns text, a small plain-English caption renders below the value.
function Section({
  title,
  stats,
  columns = 4,
  showHints = true,
}: {
  title: string;
  stats: StatDef[];
  columns?: 3 | 4;
  showHints?: boolean;
}) {
  const gridClass =
    columns === 3
      ? "grid grid-cols-2 md:grid-cols-3 gap-x-5 gap-y-4"
      : "grid grid-cols-2 md:grid-cols-4 gap-x-5 gap-y-4";
  return (
    <div>
      <div className="eyebrow mb-3">{title}</div>
      <div className={gridClass}>
        {stats.map((s) => {
          const empty = isEmpty(s.value);
          const display = empty ? NOT_DOCUMENTED : s.value;
          const hint = !empty
            ? (s.hint ?? (showHints ? explainStat(s.label, s.value) : null))
            : null;
          return (
            <div
              key={s.label}
              className={
                s.wide ? "col-span-2 md:col-span-4 min-w-0" : "min-w-0"
              }
            >
              <div className="eyebrow-xs">{s.label}</div>
              <div
                className={`mt-0.5 text-sm leading-snug truncate ${
                  empty ? "text-neutral-400 italic" : "text-black"
                } ${s.mono && !empty ? "font-mono tabular-nums" : ""}`}
                title={display ?? undefined}
              >
                {display}
              </div>
              {hint ? (
                <div className="mt-1 text-[11px] leading-snug text-neutral-500">
                  {hint}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PatientProfileCard({ caseData }: { caseData: PatientCase }) {
  const { pathology: p, intake: i, enrichment: e, mutations } = caseData;

  const cancerType =
    prettyEnum(caseData.primary_cancer_type) ||
    prettyEnum(p.primary_cancer_type) ||
    null;
  const isMelanoma =
    (caseData.primary_cancer_type || p.primary_cancer_type) ===
    "cutaneous_melanoma";

  // ── Identity (read from caseData.demographics when an intake/registration
  // sheet was uploaded; synthesize MRN/DOB only as a fallback so the banner
  // always has a value to show).
  const d = caseData.demographics;
  const displayName = formatFullName(cleanString(d?.full_name));
  const sex = formatSex(cleanString(d?.sex));
  const dob = cleanString(d?.date_of_birth) ?? synthesizeDob(i.age_years);
  const mrn = cleanString(d?.mrn) ?? synthesizeMrn(caseData.case_id);
  const raceEthnicity = joinMeta([
    cleanString(d?.race),
    cleanString(d?.ethnicity),
  ]);
  const preferredLanguage = cleanString(d?.preferred_language);
  const maritalStatus = cleanString(d?.marital_status);
  const phone = cleanString(d?.phone);
  const email = cleanString(d?.email);
  const address = cleanString(d?.address);
  const pcpName = cleanString(d?.primary_care_provider);
  const emergencyContact = cleanString(d?.emergency_contact);
  const insurance = cleanString(d?.insurance);
  const initials = deriveInitials(displayName);

  // ── Clinical values
  const breslow =
    p.breslow_thickness_mm != null ? `${p.breslow_thickness_mm} mm` : null;
  const mitotic =
    p.mitotic_rate_per_mm2 != null ? `${p.mitotic_rate_per_mm2}/mm²` : null;
  const lag3 =
    p.lag3_ihc_percent != null ? `${Math.round(p.lag3_ihc_percent)}%` : null;
  const tmb =
    e?.tmb_mut_per_mb != null ? `${e.tmb_mut_per_mb.toFixed(1)} mut/Mb` : null;
  const uv =
    e?.uv_signature_fraction != null
      ? `${Math.round(e.uv_signature_fraction * 100)}%`
      : null;
  const priorTherapies =
    e?.prior_systemic_therapies && e.prior_systemic_therapies.length > 0
      ? e.prior_systemic_therapies.join(", ")
      : i.prior_systemic_therapy === false
        ? "Treatment-naive"
        : i.prior_systemic_therapy === true
          ? "Yes (agents not specified)"
          : null;

  const mutationList =
    mutations && mutations.length > 0
      ? mutations
          .slice(0, 4)
          .map((m) => `${m.gene} ${m.ref_aa}${m.position ?? ""}${m.alt_aa}`)
          .join(", ") +
        (mutations.length > 4 ? ` +${mutations.length - 4}` : "")
      : null;

  const measurable = prettyBool(i.measurable_disease_recist);
  const priorAntiPd1 = prettyBool(i.prior_anti_pd1);
  const lifeExp =
    i.life_expectancy_months != null ? `${i.life_expectancy_months} mo` : null;
  const ageValue = i.age_years != null ? `${i.age_years} y` : null;
  const ecogValue = i.ecog != null ? `ECOG ${i.ecog}` : null;

  const pathologyStats: StatDef[] = [
    { label: "Histology", value: prettyEnum(p.histology) },
    { label: "Primary site", value: prettyEnum(p.primary_site) },
    { label: "AJCC stage", value: formatStage(i.ajcc_stage), mono: true },
    { label: "Laterality", value: null },
    ...(isMelanoma
      ? [
          {
            label: "Subtype",
            value: prettyEnum(p.melanoma_subtype),
          } as StatDef,
          { label: "Breslow", value: breslow, mono: true } as StatDef,
          { label: "Ulceration", value: prettyBool(p.ulceration) } as StatDef,
          { label: "Mitotic rate", value: mitotic, mono: true } as StatDef,
          { label: "TILs", value: prettyEnum(p.tils_present) } as StatDef,
        ]
      : []),
  ];

  const biomarkerStats: StatDef[] = [
    { label: "PD-L1", value: prettyEnum(p.pdl1_estimate) },
    { label: "TMB", value: tmb, mono: true },
    ...(isMelanoma
      ? [
          { label: "LAG-3 IHC", value: lag3, mono: true } as StatDef,
          { label: "UV signature", value: uv, mono: true } as StatDef,
        ]
      : []),
    { label: "Driver mutations", value: mutationList, mono: true, wide: true },
  ];

  return (
    <section className="card overflow-hidden">
      {/* ─── Identity banner (EHR-style) ─────────────────────────── */}
      <div className="flex items-start gap-4 px-5 py-4 border-b border-neutral-200 bg-neutral-50/60">
        {/* Avatar disc with initials */}
        <div className="shrink-0 h-14 w-14 rounded-full bg-white border border-neutral-300 flex items-center justify-center">
          <span className="font-mono text-sm tracking-wider text-neutral-500">
            {initials}
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <h2
              className={`text-xl font-semibold tracking-tight leading-tight ${
                displayName ? "text-black" : "text-neutral-400 italic"
              }`}
            >
              {displayName ?? "Name not documented"}
            </h2>
          </div>

          {/* Quick-look chart meta row: sex · age · DOB · race · language */}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-neutral-600">
            <span className={sex ? "" : "text-neutral-400 italic"}>
              {sex ?? "Sex not documented"}
            </span>
            <span className="text-neutral-300">·</span>
            <span
              className={
                ageValue ? "font-mono tabular-nums" : "text-neutral-400 italic"
              }
            >
              {ageValue ?? "Age unknown"}
            </span>
            <span className="text-neutral-300">·</span>
            <span
              className={
                dob ? "font-mono tabular-nums" : "text-neutral-400 italic"
              }
            >
              DOB {dob ?? "—"}
            </span>
            <span className="text-neutral-300">·</span>
            <span className={raceEthnicity ? "" : "text-neutral-400 italic"}>
              {raceEthnicity ?? "Race not documented"}
            </span>
            <span className="text-neutral-300">·</span>
            <span
              className={preferredLanguage ? "" : "text-neutral-400 italic"}
            >
              {preferredLanguage ?? "Language not documented"}
            </span>
          </div>

          {/* Chart identifiers row */}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono tabular-nums text-neutral-500">
            <span>
              <span className="text-neutral-400">MRN</span> {mrn}
            </span>
            <span>
              <span className="text-neutral-400">Case</span> {caseData.case_id}
            </span>
            <span>
              <span className="text-neutral-400">Dx</span>{" "}
              <span className="text-black">
                {cancerType ?? "Pending"}
                {formatStage(i.ajcc_stage)
                  ? ` · Stage ${formatStage(i.ajcc_stage)}`
                  : ""}
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* ─── Clinical sections ───────────────────────────────────── */}
      <div className="p-5 space-y-5">
        <Section
          title="Demographics"
          showHints={false}
          stats={[
            { label: "Legal sex", value: sex },
            { label: "Race / Ethnicity", value: raceEthnicity },
            { label: "Preferred language", value: preferredLanguage },
            { label: "Marital status", value: maritalStatus },
            { label: "Date of birth", value: dob, mono: true },
            { label: "Age", value: ageValue, mono: true },
            { label: "Phone", value: phone, mono: true },
            { label: "Email", value: email, mono: true },
            { label: "Address", value: address, wide: true },
          ]}
        />

        <Section
          title="Care team & coverage"
          showHints={false}
          stats={[
            { label: "Primary care", value: pcpName },
            { label: "Emergency contact", value: emergencyContact },
            { label: "Insurance", value: insurance },
            {
              label: "Documents on file",
              value: `${caseData.documents.length}`,
              mono: true,
            },
          ]}
        />

        <Section
          title="Performance & disease status"
          stats={[
            { label: "ECOG", value: ecogValue, mono: true },
            { label: "Measurable (RECIST)", value: measurable },
            { label: "Life expectancy", value: lifeExp, mono: true },
            {
              label: "Extraction confidence",
              value:
                p.confidence != null
                  ? `${Math.round(p.confidence * 100)}%`
                  : null,
              mono: true,
            },
          ]}
        />

        <Section title="Pathology" stats={pathologyStats} />

        {(p.breslow_thickness_mm != null || e?.tmb_mut_per_mb != null) && (
          <div>
            <div className="flex items-center gap-3 mb-3">
              <span className="eyebrow">Quantitative readout</span>
              <TickRuler className="flex-1 opacity-50" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
              {p.breslow_thickness_mm != null && (
                <div>
                  <Gauge
                    label="Breslow depth"
                    value={p.breslow_thickness_mm}
                    min={0}
                    max={6}
                    unit="mm"
                    bands={[
                      {
                        from: 0,
                        to: 1,
                        fill: "rgba(10,10,10,0.04)",
                        label: "T1",
                      },
                      {
                        from: 1,
                        to: 2,
                        fill: "rgba(10,10,10,0.08)",
                        label: "T2",
                      },
                      {
                        from: 2,
                        to: 4,
                        fill: "rgba(10,10,10,0.12)",
                        label: "T3",
                      },
                      {
                        from: 4,
                        to: 6,
                        fill: "rgba(10,10,10,0.18)",
                        label: "T4",
                      },
                    ]}
                  />
                  <p className="mt-2 text-[11px] leading-snug text-neutral-500">
                    How deep the melanoma has grown into the skin (in
                    millimeters). Thicker tumors are more likely to have spread,
                    which is why this number drives the T stage (T1 thinnest →
                    T4 thickest).
                    {` ${explainStat("Breslow", `${p.breslow_thickness_mm}`) ?? ""}`}
                  </p>
                </div>
              )}
              {e?.tmb_mut_per_mb != null && (
                <div>
                  <Gauge
                    label="TMB"
                    value={Number(e.tmb_mut_per_mb.toFixed(1))}
                    min={0}
                    max={30}
                    unit="mut/Mb"
                    threshold={{ value: 10, label: "TMB-high" }}
                    bands={[{ from: 10, to: 30, fill: "rgba(11,37,69,0.10)" }]}
                  />
                  <p className="mt-2 text-[11px] leading-snug text-neutral-500">
                    Tumor mutational burden — roughly, how many DNA mistakes the
                    tumor has per million letters of genome. More mistakes means
                    more unusual proteins for the immune system to see, so high
                    TMB tumors tend to respond better to immunotherapy.
                    {` ${explainStat("TMB", e.tmb_mut_per_mb.toFixed(1)) ?? ""}`}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        <Section title="Biomarkers & molecular" stats={biomarkerStats} />

        <Section
          title="Treatment history"
          stats={[
            {
              label: "Prior systemic therapy",
              value: priorTherapies,
              wide: true,
            },
            { label: "Prior anti-PD-1", value: priorAntiPd1 },
          ]}
          columns={3}
        />
      </div>
    </section>
  );
}
