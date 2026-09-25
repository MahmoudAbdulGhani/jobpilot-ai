'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Compass, List } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';

const links = [
  ['how-it-works', 'How it works'], ['features', 'Features'],
  ['product-preview', 'Product preview'], ['faq', 'FAQ'],
];

export function LandingHeader() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState('');
  const [scrolled, setScrolled] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const sentinel = document.getElementById('lp-top');
    const topObserver = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting));
    if (sentinel) topObserver.observe(sentinel);
    const sections = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) setActive(entry.target.id); });
    }, { rootMargin: '-15% 0px -60% 0px' });
    links.forEach(([id]) => { const el = document.getElementById(id); if (el) sections.observe(el); });
    return () => { topObserver.disconnect(); sections.disconnect(); };
  }, []);

  return <>
    <a href="#main" className="skip-link">Skip to content</a>
    <div id="lp-top" aria-hidden="true" />
    <header className={`lp-header${scrolled ? ' is-scrolled' : ''}`}>
      <div className="lp-header-inner">
        <Link href="/" className="lp-brand" aria-label="JobPilot AI home"><Compass size={31} weight="duotone" aria-hidden="true" /><span>JobPilot<span className="lp-brand-ai">AI</span></span></Link>
        <nav className="lp-desktop-nav" aria-label="Main navigation">{links.map(([id, label]) => <a key={id} href={`#${id}`} aria-current={active === id ? 'location' : undefined}>{label}</a>)}</nav>
        <div className="lp-header-actions"><Link className="lp-sign-in" href="/login">Sign in</Link><Button asChild className="lp-button lp-header-cta"><Link href="/login">Open your workspace <ArrowRight aria-hidden="true" /></Link></Button><Button ref={trigger} variant="ghost" size="icon" className="lp-menu-toggle" aria-label="Open navigation" onClick={() => setOpen(true)}><List size={24} /></Button></div>
      </div>
    </header>
    <Sheet open={open} onOpenChange={setOpen}><SheetContent className="lp-mobile-menu" onCloseAutoFocus={event => { event.preventDefault(); trigger.current?.focus(); }}><SheetHeader><SheetTitle>JobPilot AI</SheetTitle><SheetDescription>A thoughtful next step for your career.</SheetDescription></SheetHeader><nav aria-label="Mobile navigation">{links.map(([id, label]) => <a key={id} href={`#${id}`} onClick={() => setOpen(false)}>{label}<ArrowRight aria-hidden="true" /></a>)}<Link href="/login">Sign in to your workspace <ArrowRight aria-hidden="true" /></Link></nav></SheetContent></Sheet>
  </>;
}
