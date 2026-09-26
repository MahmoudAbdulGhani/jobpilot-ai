export type PackBlock = {
  id: string;
  kind: 'heading' | 'paragraph' | 'bullet';
  text: string;
};
export type PackEvidence = { fact_id: string | null; cv_quote: string | null };
export type StoredPackBlock = PackBlock & { origin: 'ai' | 'user'; evidence: PackEvidence[] };
export type PackDocument = { blocks: PackBlock[] };
export type StoredPackDocument = { blocks: StoredPackBlock[] };
export type PackVersion = {
  id: string;
  number: number;
  cv: StoredPackDocument;
  cover_letter: StoredPackDocument;
  created_at: string;
  approved_at: string | null;
};
export type ApplicationPack = {
  id: string;
  job_id: string;
  resume_id: string;
  status: 'generating' | 'ready' | 'failed';
  current_version: number;
  version: PackVersion | null;
  review_notes: string[];
  source_snapshot: {
    cv_text?: string;
    resume_name?: string;
    reviewed_at?: string;
    profile_facts?: { id: string; path: string; value: string }[];
    application_skill_facts?: { id: string; path: string; value: string }[];
    application_skills?: { id: string; skill: string; importance: string; job_quote: string; analysis_id: string }[];
    job?: { title?: string; company?: string; description?: string };
  };
  is_outdated: boolean;
  provider: string;
  model: string;
  outcome_message: string | null;
  created_at: string;
};
export type PackPage<T> = { items: T[]; total: number; page: number; page_size: number };
export type PackVersionList = PackPage<PackVersion>;
export type PackOptions = {
  provider: string;
  model: string;
  available: boolean;
  reason: string | null;
  resumes: { id: string; display_name: string; reviewed_at: string }[];
  has_profile: boolean;
  has_description: boolean;
};

// Evidence, origins and audit fields always come from the server, never a save payload.
export function editableDocument(document: StoredPackDocument): PackDocument {
  return { blocks: document.blocks.map(({ id, kind, text }) => ({ id, kind, text })) };
}
