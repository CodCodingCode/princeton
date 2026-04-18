// Mirror of backend/src/neoantigen/models.py — kept manually in sync.

export interface Mutation {
  gene: string;
  ref_aa: string;
  position: number;
  alt_aa: string;
}

export interface PathologyFindings {
  primary_cancer_type: string;
  histology: string;
  primary_site: string;
  melanoma_subtype: string;
  breslow_thickness_mm: number | null;
  ulceration: boolean | null;
  mitotic_rate_per_mm2: number | null;
  tils_present: string;
  pdl1_estimate: string;
  lag3_ihc_percent: number | null;
  confidence: number;
  notes: string;
}

export interface ClinicianIntake {
  ecog: number | null;
  lag3_ihc_percent: number | null;
  measurable_disease_recist: boolean | null;
  life_expectancy_months: number | null;
  prior_systemic_therapy: boolean | null;
  prior_anti_pd1: boolean | null;
  ajcc_stage: string | null;
  age_years: number | null;
}

export interface EnrichedBiomarkers {
  tmb_mut_per_mb: number | null;
  uv_signature_fraction: number | null;
  total_snvs_scored: number | null;
  prior_systemic_therapies: string[];
  prior_anti_pd1: boolean | null;
  source_notes: Record<string, string>;
}

export interface CitationRef {
  pmid: string;
  title: string;
  year: string;
  journal: string;
  snippet: string;
  relevance: number;
}

export interface RailwayAlternative {
  option_label: string;
  option_description: string;
  reason_not_chosen: string;
  next_id: string | null;
}

export interface RailwayStep {
  node_id: string;
  title: string;
  question: string;
  chosen_option_label: string;
  chosen_option_description: string;
  chosen_next_id: string | null;
  chosen_rationale: string;
  reasoning: string;
  evidence: Record<string, string>;
  citations: CitationRef[];
  alternatives: RailwayAlternative[];
  is_terminal: boolean;
  phase_id: string;
  phase_title: string;
}

export interface RailwayMap {
  steps: RailwayStep[];
  mermaid: string;
  final_recommendation: string;
}

export type TrialStatus =
  | "eligible"
  | "ineligible"
  | "needs_more_data"
  | "unscored";

export interface TrialMatch {
  nct_id: string;
  title: string;
  sponsor: string;
  phase: string | null;
  status: TrialStatus;
  passing_criteria: string[];
  failing_criteria: string[];
  unknown_criteria: string[];
  is_regeneron: boolean;
  url: string | null;
}

export interface TrialSite {
  nct_id: string;
  facility: string;
  city: string;
  state: string;
  country: string;
  lat: number | null;
  lng: number | null;
  status: string;
}

export interface PageFinding {
  page_number: number;
  description: string;
  primary_cancer_type: string | null;
  histology: string | null;
  primary_site: string | null;
  melanoma_subtype: string | null;
  breslow_thickness_mm: number | null;
  ulceration: boolean | null;
  mitotic_rate_per_mm2: number | null;
  tils_present: string | null;
  pdl1_estimate: string | null;
  lag3_ihc_percent: number | null;
  ajcc_stage: string | null;
  age_years: number | null;
  ecog: number | null;
  measurable_disease_recist: boolean | null;
  life_expectancy_months: number | null;
  prior_systemic_therapy: boolean | null;
  prior_anti_pd1: boolean | null;
  mutations_text: string[];
  notes: string;
}

export interface DocumentExtraction {
  filename: string;
  document_kind: string;
  page_count: number;
  text_excerpt: string;
  pages: PageFinding[];
  used_vision_fallback: boolean;
}

export interface ProvenanceEntry {
  field: string;
  value: string;
  filename: string;
  page_number: number | null;
}

export interface PatientCase {
  case_id: string;
  pathology: PathologyFindings;
  primary_cancer_type: string;
  intake: ClinicianIntake;
  enrichment: EnrichedBiomarkers | null;
  mutations: Mutation[];
  documents: DocumentExtraction[];
  provenance: ProvenanceEntry[];
  conflicts: string[];
  pdf_text_excerpt: string;
  railway: RailwayMap | null;
  trial_matches: TrialMatch[];
  trial_sites: TrialSite[];
  final_recommendation: string;
}

export type EventKind =
  | "log"
  | "tool_start"
  | "tool_result"
  | "tool_error"
  | "done"
  | "thinking_delta"
  | "answer_delta"
  | "pdf_extracted"
  | "doc_extracted"
  | "aggregation_start"
  | "aggregation_done"
  | "nccn_node_visited"
  | "railway_step"
  | "railway_ready"
  | "rag_citations"
  | "trial_matches_ready"
  | "trial_sites_ready"
  | "case_update"
  | "chat_thinking_delta"
  | "chat_answer_delta"
  | "chat_tool_call"
  | "chat_tool_result"
  | "chat_ui_focus"
  | "chat_done"
  | "ping"
  | "stream_end";

export interface AgentEvent {
  kind: EventKind;
  label: string;
  payload: Record<string, unknown>;
  timestamp: number;
}
