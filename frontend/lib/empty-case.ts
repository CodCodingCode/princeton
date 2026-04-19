import type { PatientCase } from "./types";

/**
 * Stub `PatientCase` so the UI can render without a backend - useful for
 * layout work and for `/?case=anything` previews.
 */
export function emptyCase(caseId: string): PatientCase {
  return {
    case_id: caseId,
    pathology: {
      primary_cancer_type: "unknown",
      histology: "",
      primary_site: "",
      melanoma_subtype: "unknown",
      breslow_thickness_mm: null,
      ulceration: null,
      mitotic_rate_per_mm2: null,
      tils_present: "",
      pdl1_estimate: "",
      lag3_ihc_percent: null,
      confidence: 0,
      notes: "",
    },
    primary_cancer_type: "unknown",
    intake: {
      ecog: null,
      lag3_ihc_percent: null,
      measurable_disease_recist: null,
      life_expectancy_months: null,
      prior_systemic_therapy: null,
      prior_anti_pd1: null,
      ajcc_stage: null,
      age_years: null,
    },
    demographics: null,
    enrichment: null,
    mutations: [],
    documents: [],
    provenance: [],
    conflicts: [],
    pdf_text_excerpt: "",
    railway: null,
    trial_matches: [],
    trial_sites: [],
    final_recommendation: "",
  };
}
