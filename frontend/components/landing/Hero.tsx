'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { ArrowDown, ArrowUpRight, Check, CheckCircle, FileText, LockSimple, MapPin, Sparkle } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';

export function Hero() {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const media = gsap.matchMedia();
    media.add('(prefers-reduced-motion: no-preference)', () => {
      const timeline = gsap.timeline({ defaults: { ease: 'power3.out' }, delay: 0.12 });
      timeline.from('.lp-title-line > span', { yPercent: 110, stagger: .1, duration: .85 })
        .from('.lp-cv', { x: -22, y: 30, rotation: -5, opacity: 0, duration: .85 }, .25)
        .from('.lp-evidence', { backgroundSize: '0% 100%', duration: .6, stagger: .13 }, .9)
        .from('.lp-fact', { x: -35, y: 12, opacity: 0, duration: .65, stagger: .12 }, 1.15)
        .from('.lp-hero-path', { strokeDashoffset: 1, duration: .8 }, 1.25)
        .from('.lp-match', { y: 24, x: -20, rotation: 3, opacity: 0, duration: .8 }, 1.6)
        .from('.lp-review-receipt', { scale: .95, y: 18, opacity: 0, duration: .6 }, 2.1);
    }, el);
    media.add('(min-width: 1000px) and (pointer: fine) and (prefers-reduced-motion: no-preference)', () => {
      const scene = el.querySelector<HTMLElement>('.lp-scene-depth');
      const frame = el.querySelector<HTMLElement>('.lp-hero-scene');
      if (!scene || !frame) return;
      const x = gsap.quickTo(scene, 'rotationY', { duration: .7, ease: 'power2.out' });
      const y = gsap.quickTo(scene, 'rotationX', { duration: .7, ease: 'power2.out' });
      let visible = true;
      const move = (event: PointerEvent) => {
        if (!visible || event.buttons) return;
        const rect = frame.getBoundingClientRect();
        x(((event.clientX - rect.left) / rect.width - .5) * 3);
        y(((event.clientY - rect.top) / rect.height - .5) * -3);
      };
      const leave = () => { x(0); y(0); };
      const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (!visible) { x.tween.pause(); y.tween.pause(); } });
      observer.observe(frame);
      frame.addEventListener('pointermove', move);
      frame.addEventListener('pointerleave', leave);
      return () => { observer.disconnect(); frame.removeEventListener('pointermove', move); frame.removeEventListener('pointerleave', leave); x.tween.kill(); y.tween.kill(); gsap.set(scene, { clearProps: 'transform' }); };
    }, el);
    return () => media.revert();
  }, []);

  return <section className="lp-hero lp-container" ref={root} aria-labelledby="hero-title">
    <div className="lp-hero-copy">
      <p className="lp-eyebrow"><span className="lp-status-dot" /> A LITTLE DIRECTION. A WORLD OF POSSIBILITY.</p>
      <h1 id="hero-title" aria-label="Your next career move, thoughtfully prepared."><span className="lp-title-line"><span>Your next</span></span><span className="lp-title-line"><span>career move,</span></span><span className="lp-title-line lp-title-accent"><span>thoughtfully</span></span><span className="lp-title-line lp-title-accent"><span>prepared.</span></span></h1>
      <p className="lp-hero-description">Turn your experience into a clear profile, discover relevant opportunities, and prepare applications you can review and make your own.</p>
      <div className="lp-hero-actions"><Button asChild className="lp-button"><Link href="/login">Open your workspace <ArrowUpRight aria-hidden="true" /></Link></Button><a className="lp-text-link" href="#product-preview">Take a closer look <ArrowDown size={17} aria-hidden="true" /></a></div>
      <p className="lp-control-note"><LockSimple size={14} aria-hidden="true" />Your experience. Your choices. Always.</p>
    </div>
    <div className="lp-hero-scene" aria-label="Illustrative career workflow">
      <div className="lp-scene-caption"><span>FROM EXPERIENCE TO OPPORTUNITY</span><span className="lp-scene-index">01 — 04</span></div>
      <div className="lp-orbit lp-orbit-one" aria-hidden="true" /><div className="lp-orbit lp-orbit-two" aria-hidden="true" />
      <div className="lp-scene-depth">
        <svg className="lp-hero-connectors" viewBox="0 0 620 560" fill="none" aria-hidden="true"><path className="lp-hero-path" d="M180 213H342Q370 213 370 245V302Q370 320 400 320H485" pathLength="1" stroke="currentColor" strokeWidth="1.4" strokeDasharray="1" /><circle cx="180" cy="213" r="4" fill="currentColor"/><circle cx="485" cy="320" r="4" fill="currentColor"/></svg>
        <article className="lp-cv">
          <div className="lp-document-label"><FileText size={17} aria-hidden="true" /><span>THE STARTING POINT</span><span className="lp-file-ext">PDF</span></div>
          <h2>Alex Morgan</h2><p className="lp-cv-role">Product designer & thoughtful problem solver</p>
          <div className="lp-document-rule" />
          <p className="lp-card-label">A LITTLE ABOUT ME</p><p className="lp-cv-summary">Clear, human experiences.<br /><span className="lp-evidence">5 years in product design.</span><br />Curious by nature. Collaborative by default.</p>
          <p className="lp-card-label">EXPERIENCE</p><strong className="lp-cv-job">Product Designer</strong><p className="lp-cv-company">Fieldwork Studio · 2021–2026</p><p className="lp-cv-summary">Built <span className="lp-evidence">accessible design systems</span> with cross-functional teams.</p>
          <div className="lp-cv-skills"><span>Research</span><span>Figma</span><span>Design systems</span></div>
          <div className="lp-document-footer"><span>alex_morgan_cv.pdf</span><CheckCircle size={15} aria-hidden="true" /></div>
        </article>
        <div className="lp-facts"><div className="lp-fact"><span className="lp-fact-icon"><Sparkle size={17} aria-hidden="true" /></span><div><span>EXPERIENCE, CONNECTED</span><strong>5 years · Product design</strong></div><Check size={16} aria-hidden="true" /></div><div className="lp-fact lp-fact-secondary"><Check size={14} aria-hidden="true" /><span>Design systems</span><span>UX research</span></div></div>
        <article className="lp-match"><div className="lp-match-top"><span className="lp-company-mark" aria-hidden="true">f<span>·</span></span><span className="lp-match-badge"><span /> SKILLS IN COMMON</span></div><h3>Senior Product Designer</h3><p>Forma Studio <span>·</span> Design & technology</p><div className="lp-match-location"><MapPin size={14} aria-hidden="true" />London, UK <span>Remote friendly</span></div><div className="lp-match-skills"><span><Check size={12} aria-hidden="true" />Design systems</span><span><Check size={12} aria-hidden="true" />Research</span></div><div className="lp-match-bottom"><span>An opportunity worth exploring</span><ArrowUpRight size={20} aria-hidden="true" /></div></article>
        <div className="lp-review-receipt"><span className="lp-review-icon"><FileText size={18} aria-hidden="true" /></span><div><strong>A strong start. Still your story.</strong><span>Application draft ready for your review</span></div><span className="lp-receipt-check"><Check size={15} aria-hidden="true" /></span></div>
      </div>
      <p className="lp-illustrative">Illustrative product preview.</p>
    </div>
    <div className="lp-hero-bottom"><span>GOOD TOOLS DON’T TAKE THE WHEEL. THEY HELP YOU FIND YOUR WAY.</span><a href="#how-it-works">Discover the process <ArrowDown size={15} aria-hidden="true" /></a></div>
  </section>;
}
