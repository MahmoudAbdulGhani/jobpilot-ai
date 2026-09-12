export type User = { id: string; email: string; is_active: boolean };
export type Job = { id: string; owner_id: string; title: string; company: string; location: string | null; description: string | null; source_url: string | null; notes: string | null; is_archived: boolean; created_at: string; updated_at: string };
export type JobInput = Pick<Job, 'title'|'company'|'location'|'description'|'source_url'|'notes'>;
export type JobList = { items: Job[]; total: number; page: number; page_size: number };
