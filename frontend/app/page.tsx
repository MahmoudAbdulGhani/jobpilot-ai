import Link from 'next/link';
import { ArrowRight, ArrowUpRight, Check, Compass, FileText, Fingerprint, LockSimple, Microphone, NotePencil, Plus, Sparkle, Target } from '@phosphor-icons/react/dist/ssr';
import { Button } from '@/components/ui/button';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { Hero } from '@/components/landing/Hero';
import { WorkflowStory } from '@/components/landing/WorkflowStory';
import { ProductPreview } from '@/components/landing/ProductPreview';
import { ReviewControl } from '@/components/landing/ReviewControl';
import './landing.css';

export const metadata = {
  title: 'JobPilot AI — Your next career move, thoughtfully prepared',
  description: 'Turn your CV into a clear profile, discover relevant opportunities, and prepare applications you can review and make your own. AI prepares. You decide.',
};

const faqs = [
  ['What does JobPilot do with my CV?', 'Upload a PDF or DOCX and review its extracted text. Once you confirm the text, optional AI can suggest profile details. You decide which suggestions to save, and you can correct or add information yourself.'],
  ['Can I edit AI suggestions?', 'Yes. Compare suggestions with your saved profile, edit individual fields, and choose what to keep. You can also edit application drafts before approving a version for export. You do not need to regenerate suggestions to make a correction.'],
  ['Does it automatically send applications?', 'No. You review and approve application materials. Where email sending is configured, sending requires a separate explicit action after reviewing the recipient, message, and attachments. Live Gmail delivery is not yet verified. Nothing in this page’s demo is sent or saved to an account.'],
  ['Can I use it for remote jobs?', 'Yes. Discovery includes remote listings from Jobicy alongside JobTech listings, which primarily cover Sweden. Always check the original listing: remote work may still have location, time-zone, or work-authorization requirements.'],
  ['Do I need to connect Gmail?', 'No. Your profile, job discovery, application preparation, and tracking work without Gmail. Mailbox connection is optional; live Google integration remains in development and depends on configuration and provider approval.'],
  ['What happens when AI cannot identify a field?', 'Missing or unsupported details are marked for review. Add them manually or leave them unset, then review the profile before saving. An AI suggestion is a starting point, not a verified fact.'],
];

export default function Home() {
  return <div className="lp-page" data-testid="landing-page">
    <LandingHeader />
    <main id="main" tabIndex={-1}>
      <Hero />
      <WorkflowStory />
      <section id="features" className="lp-features lp-container lp-section" aria-labelledby="features-title">
        <div className="lp-section-heading"><div><p className="lp-eyebrow">A WORKSPACE WITH PURPOSE</p><h2 id="features-title">Less scattered.<br /><em>More considered.</em></h2></div><p>The right support for each part of your search.<br />All connected by one thing: you.</p></div>
        <div className="lp-feature-grid">
          <article className="lp-feature lp-feature-profile"><div className="lp-feature-top"><span className="lp-feature-icon"><Fingerprint size={24} aria-hidden="true" /></span><span className="lp-feature-number">01 / UNDERSTAND</span></div><h3>More than a document.<br />A picture of your potential.</h3><p>Bring your experience into focus. Review extracted CV text, edit suggested profile details, and fill in what makes you, you.</p><div className="lp-profile-specimen"><div className="lp-profile-avatar">AM</div><div><strong>Alex Morgan</strong><span>Product designer · 5 years of experience</span></div><span className="lp-profile-tick"><Check size={17} aria-hidden="true" /></span><div className="lp-specimen-tags"><span>Design systems</span><span>Research</span><span>Accessible design</span></div><p>Illustrative product preview.</p></div><span className="lp-feature-caption">PROFILE & CV INTELLIGENCE</span></article>
          <article className="lp-feature lp-feature-discovery"><div className="lp-feature-top"><span className="lp-feature-icon"><Target size={24} aria-hidden="true" /></span><span className="lp-feature-number">02 / DISCOVER</span></div><h3>A search with<br />a sense of direction.</h3><p>Explore sourced listings, consider the fit, and save the opportunities that deserve a closer look.</p><div className="lp-discovery-visual" aria-hidden="true"><span className="lp-radar-ring" /><span className="lp-radar-ring" /><span className="lp-radar-ring" /><span className="lp-radar-center"><Compass size={31} weight="duotone" /></span><span className="lp-radar-label lp-radar-label-one">Your skills</span><span className="lp-radar-label lp-radar-label-two">Your ambitions</span><span className="lp-radar-label lp-radar-label-three">Your next chapter</span><span className="lp-radar-dot" /></div><span className="lp-feature-caption">JOB DISCOVERY & FIT</span></article>
          <article className="lp-feature lp-feature-small"><NotePencil size={25} aria-hidden="true" /><h3>A thoughtful first impression.</h3><p>Prepare tailored CV and cover-letter drafts. Review, refine, and approve the version you want to export.</p><span className="lp-feature-caption">APPLICATION PREPARATION</span></article>
          <article className="lp-feature lp-feature-small"><FileText size={25} aria-hidden="true" /><h3>Keep your next steps together.</h3><p>Track statuses, notes, and follow-up dates in one place, with reminders inside your workspace.</p><span className="lp-feature-caption">TRACKING & FOLLOW-UPS</span></article>
          <article className="lp-feature lp-feature-small"><Microphone size={25} aria-hidden="true" /><h3>Find the words before the moment.</h3><p>Practise role-specific interview questions, save your answers, and reflect on optional AI feedback.</p><span className="lp-feature-caption">INTERVIEW PRACTICE</span></article>
        </div>
        <p className="lp-feature-availability"><Sparkle size={15} aria-hidden="true" />AI-assisted features depend on provider configuration and your consent.</p>
      </section>
      <ProductPreview />
      <ReviewControl />
      <section className="lp-privacy lp-container" aria-label="Your data and decisions"><div><LockSimple size={21} aria-hidden="true" /><h3>A private account workspace</h3><p>Your profile and career records belong to your signed-in account.</p></div><div><Check size={21} aria-hidden="true" /><h3>Review before making changes</h3><p>Review changes before saving. Sending an application requires separate approval.</p></div><div><Fingerprint size={21} aria-hidden="true" /><h3>Provider consent is optional</h3><p>Review the data, purpose, and provider before choosing an AI use.</p></div></section>
      <section id="faq" className="lp-faq lp-container lp-section" aria-labelledby="faq-title"><div className="lp-faq-intro"><p className="lp-eyebrow">A FEW THINGS, EXPLAINED</p><h2 id="faq-title">Good questions.<br /><em>Clear answers.</em></h2><p>A little clarity before you begin.</p></div><div className="lp-faq-list">{faqs.map(([question, answer], index) => <details className="lp-faq-item" key={question}><summary><span className="lp-faq-number">0{index + 1}</span><h3>{question}</h3><Plus size={19} aria-hidden="true" /></summary><div className="lp-faq-answer"><p>{answer}</p></div></details>)}</div></section>
      <section className="lp-final-cta" aria-labelledby="final-title"><div className="lp-container"><span className="lp-final-compass" aria-hidden="true"><Compass size={48} weight="duotone" /></span><p className="lp-eyebrow">YOUR NEXT CHAPTER STARTS WITH YOU</p><h2 id="final-title">Make room for<br /><em>what comes next.</em></h2><p>A clearer picture. A considered application. A step forward.</p><Button asChild className="lp-button"><Link href="/login">Open your workspace <ArrowUpRight aria-hidden="true" /></Link></Button><span className="lp-access-note">Sign in with your existing account.<br />Have an invitation? Follow the link in your invitation email.</span></div></section>
    </main>
    <footer className="lp-footer lp-container"><div className="lp-footer-main"><Link href="/" className="lp-brand"><Compass size={29} weight="duotone" aria-hidden="true" /><span>JobPilot<span className="lp-brand-ai">AI</span></span></Link><p>A little direction for your next chapter.</p><a href="#main" className="lp-back-top">Back to top <ArrowRight size={17} aria-hidden="true" /></a></div><div className="lp-footer-bottom"><span>© {new Date().getFullYear()} JobPilot AI</span><nav aria-label="Footer navigation"><a href="#how-it-works">How it works</a><a href="#your-control">Your control</a><a href="#faq">FAQ</a><Link href="/login">Sign in</Link></nav><span>Thoughtfully prepared. Always yours.</span></div></footer>
  </div>;
}
