'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, CheckCircle, PencilSimple, ShieldCheck, Sparkle } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import './preview.css';

const existingHeadline = 'Product designer';
const suggestedHeadline = 'Product designer creating thoughtful digital experiences';

export function ReviewControl() {
  const [headline, setHeadline] = useState(suggestedHeadline);
  const [selected, setSelected] = useState(true);
  const [status, setStatus] = useState<'editing' | 'approved' | 'canceled'>('editing');
  const approvalRef = useRef<HTMLDivElement>(null);
  const valid = selected && headline.trim().length > 0;

  useEffect(() => {
    if (status === 'approved') approvalRef.current?.focus();
  }, [status]);

  function reset() {
    setHeadline(suggestedHeadline);
    setSelected(true);
    setStatus('editing');
  }

  return (
    <section id="your-control" className="lp-control-section" aria-labelledby="lp-control-heading">
      <div className="lp-demo-container lp-control-grid">
        <div className="lp-control-copy">
          <p className="lp-demo-kicker">THE MOST IMPORTANT PART IS YOU</p>
          <h2 id="lp-control-heading">AI prepares.<br /><em>You decide.</em></h2>
          <p className="lp-control-lede">A helpful first draft. A clearer next step.<br />And the final say, always yours.</p>
          <div className="lp-control-principles">
            <div><PencilSimple size={21} aria-hidden="true" /><div><h3>Make every suggestion your own.</h3><p>Review the details, edit the wording, or leave a suggestion behind.</p></div></div>
            <div><ShieldCheck size={22} aria-hidden="true" /><div><h3>Move forward with intention.</h3><p>You review changes before applying them. Optional AI processing asks for your consent.</p></div></div>
          </div>
          <span className="lp-control-side-note"><span aria-hidden="true" /> A little assistance. A lot of agency.</span>
        </div>

        <div className="lp-control-demo">
          <div className="lp-control-demo-header"><span><Sparkle size={16} aria-hidden="true" /> A PROPOSAL, NOT A DECISION</span><span>01 / 01</span></div>
          <div className="lp-control-demo-body">
            <div className="lp-control-title"><h3>Sound more like you.</h3><span className="lp-control-draft-tag">{status === 'approved' ? 'REVIEWED' : 'YOUR DRAFT'}</span></div>
            <p className="lp-control-instruction">Try editing this sample profile headline.</p>
            <label htmlFor="lp-sample-headline" className="lp-control-field-label">Suggested headline</label>
            <Input id="lp-sample-headline" className="lp-control-input" value={headline} maxLength={120} disabled={status === 'approved'} onChange={event => { setHeadline(event.target.value); setStatus('editing'); }} aria-describedby="lp-headline-help" />
            <p id="lp-headline-help" className="lp-control-field-help">Keep the parts that feel right. Change the rest.</p>
            <label className="lp-control-selection" htmlFor="lp-include-headline">
              <Checkbox id="lp-include-headline" className="lp-control-checkbox" checked={selected} disabled={status === 'approved'} onCheckedChange={value => { setSelected(value === true); setStatus('editing'); }} />
              <span>Include this headline update</span>
            </label>

            <div className="lp-control-summary" aria-live="polite" aria-atomic="true">
              <div className="lp-control-summary-heading"><span>YOUR REVIEW SUMMARY</span><span>{valid ? '1 change' : 'No changes'}</span></div>
              <div className="lp-control-summary-row"><span>Current</span><p>{existingHeadline}</p></div>
              <div className="lp-control-summary-row lp-control-summary-proposed"><span>{status === 'approved' ? 'Approved' : 'After review'}</span><p>{valid ? headline.trim() : existingHeadline}</p></div>
            </div>

            {status === 'approved' ? (
              <div className="lp-control-result" role="status" tabIndex={-1} ref={approvalRef}><CheckCircle size={24} weight="fill" aria-hidden="true" /><div><strong>Approved in this demo.</strong><p>Your words. Your decision.</p></div></div>
            ) : (
              <div className="lp-control-approval-actions">
                <Button className="lp-control-approve" disabled={!valid} onClick={() => { if (valid) setStatus('approved'); }}>Approve sample change <ArrowRight size={17} aria-hidden="true" /></Button>
                <Button variant="ghost" className="lp-control-cancel" onClick={() => { setHeadline(existingHeadline); setSelected(false); setStatus('canceled'); }}>Cancel</Button>
              </div>
            )}
            {status === 'canceled' && <p className="lp-control-canceled" role="status">Changes canceled. Nothing was applied.</p>}
            <div className="lp-control-bottomline"><span><Check size={14} aria-hidden="true" /> Nothing is saved or sent.</span>{status === 'approved' ? <Button variant="ghost" className="lp-control-reset" onClick={() => setStatus('editing')}>Edit again</Button> : <Button variant="ghost" className="lp-control-reset" onClick={reset}>Reset demo</Button>}</div>
          </div>
          <p className="lp-control-preview-caption">Illustrative product preview.</p>
        </div>
      </div>
    </section>
  );
}
