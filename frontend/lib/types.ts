export type User = { id: string; email: string; is_active: boolean; onboarding_step?: string };
export type Job = { source_provider?: string | null; source_external_id?: string | null; imported_at?: string | null; source_snapshot?: {source_url: string; published_at: string | null; deadline: string | null; salary: string | null; workplace_model: string | null; test_data: boolean} | null; id: string; owner_id: string; title: string; company: string; location: string | null; description: string | null; source_url: string | null; notes: string | null; is_archived: boolean; created_at: string; updated_at: string };
export type JobInput = Pick<Job, 'title'|'company'|'location'|'description'|'source_url'|'notes'>;
export type JobList = { items: Job[]; total: number; page: number; page_size: number };

export type RemotePreference = 'office' | 'hybrid' | 'remote';
export type WorkAuthorization = 'citizen' | 'permanent_resident' | 'work_visa' | 'needs_sponsorship' | 'other';
export type LanguageProficiency = 'basic' | 'conversational' | 'professional' | 'native';
export type ExperienceEntry = { title: string; organization: string; period: string | null; notes: string | null };
export type EducationEntry = { school: string; degree: string | null; field: string | null; period: string | null };
export type LanguageEntry = { name: string; proficiency: LanguageProficiency };
export type SalaryPreference = { currency: string; min: number | null; max: number | null };
export type CandidateProfile = { id: string; owner_id: string; headline: string | null; target_roles: string[] | null; location: string | null; remote_preference: RemotePreference | null; work_authorization: WorkAuthorization | null; skills: string[] | null; experience: ExperienceEntry[] | null; education: EducationEntry[] | null; languages: LanguageEntry[] | null; salary_preference: SalaryPreference | null; created_at: string; updated_at: string };
export type CandidateProfileInput = { headline: string | null; target_roles: string[] | null; location: string | null; remote_preference: RemotePreference | null; work_authorization: WorkAuthorization | null; skills: string[] | null; experience: ExperienceEntry[] | null; education: EducationEntry[] | null; languages: LanguageEntry[] | null; salary_preference: SalaryPreference | null };

export type Resume = { id: string; owner_id: string; original_filename: string; display_name: string; file_extension: string; size_bytes: number; is_primary: boolean; created_at: string; updated_at: string };
export type ResumeList = { items: Resume[] };
export type ResumeUpdateInput = { display_name?: string; is_primary?: boolean };
export type ResumeExtraction = {
  id: string;
  resume_id: string;
  status: 'pending' | 'succeeded' | 'failed';
  original_text: string | null;
  draft_text: string | null;
  parser_name: string | null;
  parser_version: string | null;
  failure_code: string | null;
  failure_message: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};
export type ProfileSuggestion = {
  id: string;
  field: 'headline'|'location'|'skills'|'experience'|'education'|'languages';
  value: unknown;
  evidence: Array<{ quote: string }>;
};
export type ProfileSuggestionSet = {
  id: string; resume_id: string; status: 'generating'|'ready'|'failed'|'applied';
  suggestions: ProfileSuggestion[] | null; provider: string; model: string;
  outcome_message: string | null; applied_at: string | null;
};
export type JobFitRequirement = {
  id: string; text: string; job_quote: string;
  importance: 'required'|'preferred'|'unspecified';
  assessment: 'supported'|'partially_supported'|'not_evidenced'|'needs_clarification'|'explicit_mismatch';
  explanation: string; candidate_fact_ids: string[];
};
export type JobFitAnalysis = {
  id: string; job_id: string; status: 'generating'|'ready'|'failed';
  job_snapshot: Record<string, string|null>;
  profile_facts: Array<{id:string;path:string;value:string}>;
  result: {requirements:JobFitRequirement[];strengths:string[];gaps:string[];actions:string[];summary:string}|null;
  counts: Record<string,number>; provider:string; model:string; prompt_version:string;
  outcome_message:string|null; is_outdated:boolean; created_at:string; updated_at:string;
};
export type JobFitAnalysisList = {items:JobFitAnalysis[];total:number;page:number;page_size:number};

export type ApplicationMethod = 'email'|'employer_website'|'linkedin_manual'|'other';
export type ApplicationStatus = 'Applied'|'Interview'|'Offer'|'Accepted'|'Rejected'|'Withdrawn';
export type ApplicationRecord = {
  id: string; owner_id: string; job_id: string; submission_date: string;
  method: ApplicationMethod; notes: string | null; status: ApplicationStatus;
  follow_up_date: string | null; reminder_status?: string | null; reminder_timezone?: string | null; pack_id: string | null; pack_version: number | null;
  cv_snapshot: unknown | null; cover_letter_snapshot: unknown | null;
  created_at: string; updated_at: string;
};
export type ApplicationRecordList = { items: ApplicationRecord[]; total: number; page: number; page_size: number };
export type ApplicationEvent = {
  id: string; application_id: string; status: ApplicationStatus; changed_at: string;
  created_at: string; updated_at: string;
};
export type ApplicationEventList = { items: ApplicationEvent[]; total: number; page: number; page_size: number };
