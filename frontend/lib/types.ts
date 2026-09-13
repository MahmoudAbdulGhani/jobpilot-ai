export type User = { id: string; email: string; is_active: boolean };
export type Job = { id: string; owner_id: string; title: string; company: string; location: string | null; description: string | null; source_url: string | null; notes: string | null; is_archived: boolean; created_at: string; updated_at: string };
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
