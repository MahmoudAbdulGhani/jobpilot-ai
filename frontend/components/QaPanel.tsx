'use client';
import Link from 'next/link';
import { useState } from 'react';
import { api } from '../lib/api';
import { FormField } from './ui/form-field';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Alert } from './ui/alert';

type Citation = { entity: string; id: string; field: string; excerpt: string; href: string };
type Answer = {
  entity: string;
  question: string;
  source: 'ai' | 'structured';
  answer: string;
  citations: Citation[];
  matches: Citation[];
  total: number;
  limit: number;
  provider: string | null;
  model: string | null;
  reason: string | null;
};
const ENTITIES = ['jobs', 'applications', 'reminders', 'replies', 'interviews', 'profile', 'packs'];
const selectClass = 'h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50';

export function QaPanel() {
  const [entity, setEntity] = useState('jobs');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function ask() {
    if (!question.trim()) return;
    setBusy(true);
    setError('');
    try {
      const result = await api<Answer>(`/qa/answer?entity=${entity}&q=${encodeURIComponent(question)}&limit=10`);
      setAnswer(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="rounded-lg border border-border bg-card p-6" aria-label="Ask your journal">
    <div className="flex flex-col gap-2">
      <p className="text-xs font-semibold uppercase tracking-[0.04em] text-[var(--forest)]">Read-only Q&A</p>
      <h2 className="font-serif text-3xl leading-snug text-[var(--ink)]">Ask your journal</h2>
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">Answers come from your own data only (AI-enabled when you consent and the provider is configured). This never writes, sends, changes status or deletes anything. Every match cites its source.</p>
    </div>
    {error && <Alert variant="destructive" className="mt-4">{error}</Alert>}
    <form className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,220px)_1fr_auto]" onSubmit={e => { e.preventDefault(); void ask(); }}>
      <FormField label="Scope" htmlFor="qa-scope">
        <select id="qa-scope" className={selectClass} value={entity} disabled={busy} onChange={e => setEntity(e.target.value)}>
          {ENTITIES.map(item => <option key={item} value={item}>{item}</option>)}
        </select>
      </FormField>
      <FormField label="Question" htmlFor="qa-question">
        <Input id="qa-question" value={question} maxLength={500} disabled={busy} onChange={e => setQuestion(e.target.value)} placeholder="e.g. Python applications" />
      </FormField>
      <div className="flex items-end"><Button disabled={busy || !question.trim()}>{busy ? 'Searching…' : 'Ask'}</Button></div>
    </form>
    {answer && <div className="mt-4 space-y-4">
      <p className="text-sm text-muted-foreground">{answer.source === 'ai' ? `AI answer · ${answer.provider ?? 'AI'} · ${answer.model ?? ''}` : `Structured search${answer.reason ? ` · ${answer.reason}` : ''}`}</p>
      {answer.answer ? <p className="[overflow-wrap:anywhere]">{answer.answer}</p> : <p className="text-sm text-muted-foreground">No answer text.</p>}
      <p className="text-sm text-muted-foreground">{answer.total} {answer.total === 1 ? 'match' : 'matches'} in {answer.entity} (showing up to {answer.limit}).</p>
      {answer.matches.length === 0 && <p className="text-sm text-muted-foreground">No matches in your {answer.entity}.</p>}
      {answer.matches.length > 0 && <ul className="grid list-disc gap-2 pl-6 text-sm text-muted-foreground">
        {answer.matches.map(match => <li key={`${match.entity}-${match.id}-${match.field}`} className="[overflow-wrap:anywhere]">
          <strong className="font-semibold text-foreground">{match.field}</strong>: {match.excerpt || 'No excerpt.'} <Link className="text-[var(--forest)] underline underline-offset-4 hover:text-[var(--forest-hover)]" href={match.href}>Open source</Link>
        </li>)}
      </ul>}
    </div>}
  </section>;
}