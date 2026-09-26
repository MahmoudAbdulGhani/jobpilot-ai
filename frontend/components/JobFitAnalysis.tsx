'use client';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowClockwise, CheckCircle, Sparkle, Trash, WarningCircle } from '@phosphor-icons/react';
import { MeteredButton } from './MeteredButton';
import { ConfirmDialog } from './ui/confirm-dialog';
import { api } from '../lib/api';
import type { Job, JobFitAnalysis as Analysis, JobFitAnalysisList } from '../lib/types';

type SelectedSkill = { id: string; analysis_id: string; skill: string; importance: string; job_quote: string };
type Gap = { skill: string; importance: string; requirement_id: string; quotes: string[] };

export function JobFitAnalysis({ job }: { job: Job }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [history, setHistory] = useState<Analysis[]>([]);
  const [selected, setSelected] = useState<SelectedSkill[]>([]);
  const [busy, setBusy] = useState(false);
  const [skillBusy, setSkillBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');
  const skillUrl = `/jobs/${job.id}/application-skills`;

  const load = useCallback(async () => {
    const [latest, list, skills] = await Promise.allSettled([
      api<Analysis>(`/jobs/${job.id}/fit-analyses/latest`),
      api<JobFitAnalysisList>(`/jobs/${job.id}/fit-analyses?page_size=10`),
      api<{ items: SelectedSkill[] }>(skillUrl),
    ]);
    setAnalysis(latest.status === 'fulfilled' ? latest.value : null);
    setHistory(list.status === 'fulfilled' ? list.value.items : []);
    setSelected(skills.status === 'fulfilled' ? skills.value.items : []);
  }, [job.id, skillUrl]);
  useEffect(() => { void load(); }, [load, job.description, job.updated_at]);

  const gaps = useMemo(() => {
    const grouped = new Map<string, Gap>();
    for (const item of analysis?.result?.missing_skills || []) {
      const key = item.skill.trim().toLocaleLowerCase();
      if (!key) continue;
      const existing = grouped.get(key);
      if (existing) {
        if (item.importance === 'required' && existing.importance !== 'required') {
          existing.importance = 'required';
          existing.requirement_id = item.requirement_id;
        }
        if (!existing.quotes.includes(item.job_quote)) existing.quotes.push(item.job_quote);
      } else grouped.set(key, { skill: item.skill.trim(), importance: item.importance,
        requirement_id: item.requirement_id, quotes: [item.job_quote] });
    }
    return [...grouped.values()].sort((a, b) => Number(b.importance === 'required') - Number(a.importance === 'required') || a.skill.localeCompare(b.skill));
  }, [analysis]);

  async function generate() {
    setBusy(true); setError('');
    try {
      await api<Analysis>(`/jobs/${job.id}/fit-analyses`, { method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID() }) });
      await load();
      window.dispatchEvent(new Event('jobpilot:job-fit-updated'));
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Analysis failed. Try again.'); }
    finally { setBusy(false); }
  }
  async function confirm(gap: Gap) {
    if (!analysis) return;
    setSkillBusy(true); setError('');
    try {
      await api<SelectedSkill>(skillUrl, { method: 'POST', body: JSON.stringify({ analysis_id: analysis.id,
        requirement_id: gap.requirement_id, confirmed: true }) });
      await load();
      window.dispatchEvent(new Event('jobpilot:application-skills-updated'));
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not confirm this skill.'); }
    finally { setSkillBusy(false); }
  }
  async function removeSkill(item: SelectedSkill) {
    setSkillBusy(true); setError('');
    try {
      await api(`${skillUrl}/${item.id}`, { method: 'DELETE' });
      await load();
      window.dispatchEvent(new Event('jobpilot:application-skills-updated'));
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not remove this skill.'); }
    finally { setSkillBusy(false); }
  }
  async function removeAnalysis(item: Analysis) {
    setDeleting(true); setError('');
    try { await api(`/jobs/${job.id}/fit-analyses/${item.id}`, { method: 'DELETE' }); await load();
      window.dispatchEvent(new Event('jobpilot:job-fit-updated'));
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not delete this analysis.'); }
    finally { setDeleting(false); }
  }

  const current = analysis?.status === 'ready' && !!analysis.result && !analysis.is_outdated;
  return <section className="fit-analysis" aria-labelledby="fit-heading">
    <div className="fit-heading-row"><div><p className="eyebrow">Skills to review</p><h2 id="fit-heading">Skills for this role</h2></div>
      <MeteredButton feature="fit" className="primary-button" disabled={busy || deleting || !job.description?.trim()} onClick={() => void generate()}>
        {busy ? <ArrowClockwise className="spin" size={19} /> : <Sparkle size={19} />}{analysis ? 'Reanalyze fit' : 'Analyze fit'}
      </MeteredButton></div>
    <p className="muted fit-disclosure">Analysis checks the saved job description against relevant profile facts. It does not use CV files, notes or contact details. A skill shown here is not evidenced in your saved profile; that does not mean you lack it.</p>
    {!job.description?.trim() && <div className="fit-prerequisite"><WarningCircle size={20} />{job.source_provider ? 'This listing has no job description to analyze.' : 'Save a job description before analyzing fit.'}</div>}
    {busy && <p role="status">Analyzing job skills…</p>}
    {error && <div className="form-error" role="alert">{error} {error.includes('AI data-use consent is required') && <Link href="/settings#privacy">Allow selected job AI use in Privacy settings</Link>}</div>}
    {analysis?.status === 'failed' && <div className="fit-prerequisite" role="alert"><WarningCircle size={20} />{analysis.outcome_message || 'Analysis failed. Try again.'}</div>}
    {analysis?.is_outdated && <div className="fit-prerequisite" role="status"><WarningCircle size={20} />Job or profile information changed. Reanalyze before confirming skills or generating a pack.</div>}
    {current && <section className="fit-skill-section" aria-label="Skills not evidenced in your saved profile">
      <div className="fit-skill-intro"><div><h3>Not evidenced in your saved profile</h3><p>Confirm only skills you actually have. Confirmations apply to this job only and can be removed before generating a new pack.</p></div><span className="fit-skill-count">{gaps.length} to review</span></div>
      {gaps.length ? <div className="fit-skill-list">{gaps.map(gap => {
        const saved = selected.find(item => item.skill.toLocaleLowerCase() === gap.skill.toLocaleLowerCase());
        return <article className="fit-skill-card" key={gap.skill.toLocaleLowerCase()}>
          <div className="fit-skill-card-head"><h4>{gap.skill}</h4><span className={`fit-skill-priority is-${gap.importance}`}>{gap.importance === 'required' ? 'Required' : 'Preferred'}</span></div>
          <div className="fit-skill-evidence"><span>From the job posting</span>{gap.quotes.map(quote => <blockquote key={quote}>“{quote}”</blockquote>)}</div>
          {saved ? <div className="fit-skill-action"><span role="status"><CheckCircle size={18} />Confirmed for this application</span><button className="text-button" disabled={skillBusy} onClick={() => void removeSkill(saved)}>Remove</button></div>
            : <ConfirmDialog title={`Confirm ${gap.skill} for this application?`} description="Confirm only if you actually have this skill. It can appear in this job's CV and cover letter; it will not be added to your global profile." confirmLabel={`Confirm ${gap.skill}`} busy={skillBusy} onConfirm={() => void confirm(gap)} trigger={<button className="secondary-button" disabled={skillBusy}>I have this skill</button>} />}
        </article>;
      })}</div> : <div className="fit-skill-empty"><CheckCircle size={24} /><div><strong>No skills need confirmation from this analysis.</strong><p>This does not assess every qualification or guarantee eligibility. Review the full job posting before applying.</p></div></div>}
    </section>}
    {history.length > 0 && <details className="fit-history"><summary>Previous analyses ({history.length})</summary>{history.map(item => <div key={item.id}><span>{new Date(item.created_at).toLocaleString()}{item.is_outdated ? ' · Outdated' : ''}</span><ConfirmDialog title="Delete this saved fit analysis?" description="This removes the analysis and its job-specific skill confirmations. Your job and profile remain." confirmLabel="Delete analysis" destructive busy={deleting} onConfirm={() => void removeAnalysis(item)} trigger={<button className="icon-button" disabled={busy || deleting} aria-label={`Delete analysis from ${new Date(item.created_at).toLocaleString()}`}><Trash size={18} /></button>} /></div>)}</details>}
  </section>;
}
