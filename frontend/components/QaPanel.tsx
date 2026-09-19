'use client';
import Link from 'next/link';
import { useState } from 'react';
import { api } from '../lib/api';

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

  return <section className="qa-panel" aria-label="Ask your journal">
    <div className="section-title"><div>
      <p className="eyebrow">Read-only Q&A</p>
      <h2>Ask your journal</h2>
      <p className="muted">Answers come from your own data only (AI-enabled when you consent and the provider is configured). This never writes, sends, changes status or deletes anything. Every match cites its source.</p>
    </div></div>
    {error && <p className="notice form-error" role="alert">{error}</p>}
    <div className="qa-controls">
      <label><span>Scope</span><select value={entity} onChange={e => setEntity(e.target.value)}>
        {ENTITIES.map(item => <option key={item} value={item}>{item}</option>)}
      </select></label>
      <label><span>Question</span><input value={question} maxLength={500} onChange={e => setQuestion(e.target.value)} placeholder="e.g. Python applications" /></label>
      <button className="primary-button" disabled={busy || !question.trim()} onClick={() => void ask()}>{busy ? 'Searching…' : 'Ask'}</button>
    </div>
    {answer && <>
      <div className="qa-answer">
        <p className="source-badge">{answer.source === 'ai' ? `AI answer · ${answer.provider ?? 'AI'} · ${answer.model ?? ''}` : `Structured search${answer.reason ? ` · ${answer.reason}` : ''}`}</p>
        {answer.answer ? <p>{answer.answer}</p> : <p className="notice empty-state">No answer text.</p>}
      </div>
      <p className="muted">{answer.total} {answer.total === 1 ? 'match' : 'matches'} in {answer.entity} (showing up to {answer.limit}).</p>
      {answer.matches.length === 0 && <p className="notice empty-state">No matches in your {answer.entity}.</p>}
      <ul className="qa-matches">
        {answer.matches.map(match => <li key={`${match.entity}-${match.id}-${match.field}`}>
          <p><strong>{match.field}</strong>: {match.excerpt || 'No excerpt.'}</p>
          <p><Link href={match.href}>Open source</Link></p>
        </li>)}
      </ul>
    </>}
  </section>;
}