'use client';

import { useEffect, useRef } from 'react';
import { ArrowRight, ArrowUpRight, Briefcase, Check, CheckCircle, FileText, GraduationCap, MapPin, PencilSimple, Sparkle } from '@phosphor-icons/react';
import './workflow.css';

const chapters = [
  { title: 'Understand your experience', label: 'Your experience', copy: 'Start with what you already bring. Your CV becomes the evidence behind your next move.' },
  { title: 'Build a profile that sounds like you', label: 'Your profile', copy: 'Turn that experience into a clear profile. Review the details, fill the gaps, make it yours.' },
  { title: 'Find a more considered fit', label: 'Your opportunities', copy: 'Look beyond the job title. Explore opportunities alongside the skills and preferences that matter to you.' },
  { title: 'Prepare it. Then make it yours.', label: 'Your application', copy: 'Bring your relevant experience into focus. Read, edit, and approve the next step yourself.' },
  { title: 'Keep the next step in sight', label: 'Your next step', copy: 'Keep your applications and follow-ups together, with room to prepare for the conversation ahead.' },
];

function Connector({ variant = 0 }: { variant?: number }) {
  return (
    <svg className="lp-workflow-connector" viewBox="0 0 640 340" preserveAspectRatio="none" aria-hidden="true">
      <path className="lp-workflow-connector-base" d={variant % 2 === 0 ? 'M 210 132 H 286 Q 308 132 308 154 V 190 Q 308 212 330 212 H 416' : 'M 212 211 H 283 Q 308 211 308 187 V 150 Q 308 132 330 132 H 420'} />
      <path className="lp-workflow-connector-draw" d={variant % 2 === 0 ? 'M 210 132 H 286 Q 308 132 308 154 V 190 Q 308 212 330 212 H 416' : 'M 212 211 H 283 Q 308 211 308 187 V 150 Q 308 132 330 132 H 420'} />
      <circle className="lp-workflow-connector-dot" cx="308" cy="172" r="5" />
    </svg>
  );
}

function Tag({ children, quiet = false }: { children: React.ReactNode; quiet?: boolean }) {
  return <span className={`lp-workflow-tag${quiet ? ' is-quiet' : ''}`}>{children}</span>;
}

function SceneHeading({ index }: { index: number }) {
  return <div className="lp-workflow-scene-heading"><span>0{index + 1} / {chapters[index].label}</span><h3>{chapters[index].title}</h3><p>{chapters[index].copy}</p></div>;
}

function ExperienceScene() {
  return (
    <article className="lp-workflow-scene" data-workflow-scene="0" aria-label="Step 1: Understand your experience">
      <SceneHeading index={0} />
      <div className="lp-workflow-scene-grid">
        <Connector />
        <div className="lp-workflow-document lp-workflow-piece">
          <div className="lp-workflow-document-top"><FileText size={17} weight="light" /><span>MAYA_CHEN_CV.PDF</span><span>01</span></div>
          <h4>Maya Chen</h4><p className="lp-workflow-document-role">Product designer</p>
          <div className="lp-workflow-rule" />
          <p className="lp-workflow-eyebrow">EXPERIENCE</p>
          <h5>Making complex things feel simple.</h5>
          <p className="lp-workflow-document-text">Five years creating thoughtful digital products, from <mark className="lp-workflow-evidence">user research</mark> to <mark className="lp-workflow-evidence">design systems</mark>.</p>
          <div className="lp-workflow-text-lines" aria-hidden="true"><i /><i /><i /></div>
          <div className="lp-workflow-document-bottom"><GraduationCap size={15} /><span>BA, Communication Design</span></div>
        </div>
        <div className="lp-workflow-insight lp-workflow-piece">
          <span className="lp-workflow-insight-icon"><Sparkle size={22} weight="light" /></span>
          <p className="lp-workflow-eyebrow">THE DETAILS THAT MATTER</p>
          <h4>Experience,<br />with context.</h4>
          <div className="lp-workflow-fact"><Check size={14} /><span>5 years in product design</span></div>
          <div className="lp-workflow-fact"><Check size={14} /><span>Research → delivery</span></div>
          <div className="lp-workflow-fact"><Check size={14} /><span>Systems thinking</span></div>
          <p className="lp-workflow-small-note">Drawn from your CV.<br />Ready for you to check.</p>
        </div>
      </div>
    </article>
  );
}

function ProfileScene() {
  return (
    <article className="lp-workflow-scene" data-workflow-scene="1" aria-label="Step 2: Build your profile">
      <SceneHeading index={1} />
      <div className="lp-workflow-scene-grid">
        <Connector variant={1} />
        <div className="lp-workflow-profile lp-workflow-piece">
          <div className="lp-workflow-profile-head"><span className="lp-workflow-avatar">MC</span><span className="lp-workflow-status"><span />Your profile</span></div>
          <h4>Maya Chen</h4>
          <p className="lp-workflow-profile-headline">Product designer.<br />Curious by nature.</p>
          <p className="lp-workflow-document-text">Turning research into useful, considered digital experiences.</p>
          <div className="lp-workflow-rule" />
          <div className="lp-workflow-fact"><MapPin size={15} /><span>London · Open to remote</span></div>
          <div className="lp-workflow-source"><FileText size={13} /> Based on MAYA_CHEN_CV.PDF</div>
        </div>
        <div className="lp-workflow-profile-details lp-workflow-piece">
          <div className="lp-workflow-detail"><p className="lp-workflow-eyebrow">YOUR SKILLS</p><div className="lp-workflow-tags"><Tag>User research</Tag><Tag>Design systems</Tag><Tag>Prototyping</Tag></div></div>
          <div className="lp-workflow-detail"><p className="lp-workflow-eyebrow"><Briefcase size={14} /> EXPERIENCE</p><h5>Product design</h5><p>5 years · Research to delivery</p></div>
          <div className="lp-workflow-detail"><p className="lp-workflow-eyebrow"><GraduationCap size={14} /> EDUCATION</p><h5>Communication Design</h5><p>Bachelor of Arts</p></div>
          <span className="lp-workflow-edit-note"><PencilSimple size={14} /> Every detail is yours to edit.</span>
        </div>
      </div>
    </article>
  );
}

function OpportunitiesScene() {
  return (
    <article className="lp-workflow-scene" data-workflow-scene="2" aria-label="Step 3: Discover relevant opportunities">
      <SceneHeading index={2} />
      <div className="lp-workflow-scene-grid lp-workflow-opportunity-grid">
        <Connector />
        <div className="lp-workflow-preferences lp-workflow-piece">
          <p className="lp-workflow-eyebrow">A SEARCH SHAPED BY YOU</p><h4>A thoughtful<br />next move.</h4>
          <dl><div><dt>Role</dt><dd>Product designer</dd></div><div><dt>Location</dt><dd>London or remote</dd></div><div><dt>Bring forward</dt><dd>User research<br />Design systems</dd></div></dl>
          <span className="lp-workflow-source"><span className="lp-workflow-mini-avatar">MC</span> From your reviewed profile</span>
        </div>
        <div className="lp-workflow-jobs lp-workflow-piece">
          <div className="lp-workflow-job is-primary"><div className="lp-workflow-job-top"><span className="lp-workflow-company">f.</span><span>Fieldwork Studio<small>Sample company</small></span><ArrowUpRight size={17} /></div><h4>Senior Product Designer</h4><p className="lp-workflow-job-location"><MapPin size={13} /> London <span>·</span> Remote-friendly</p><div className="lp-workflow-tags"><Tag>User research</Tag><Tag>Design systems</Tag></div><div className="lp-workflow-match"><CheckCircle size={14} /> Relevant experience in your profile</div></div>
          <div className="lp-workflow-job is-secondary"><div className="lp-workflow-job-top"><span className="lp-workflow-company">a.</span><span>Arc & Co.<small>Sample company</small></span></div><h4>Product Designer</h4><p className="lp-workflow-job-location"><MapPin size={13} /> Remote <span>·</span> Europe</p><div className="lp-workflow-tags"><Tag quiet>Prototyping</Tag><Tag quiet>User research</Tag></div></div>
        </div>
      </div>
    </article>
  );
}

function ReviewScene() {
  return (
    <article className="lp-workflow-scene" data-workflow-scene="3" aria-label="Step 4: Prepare and review an application">
      <SceneHeading index={3} />
      <div className="lp-workflow-scene-grid lp-workflow-review-grid">
        <Connector variant={1} />
        <div className="lp-workflow-role-summary lp-workflow-piece"><span className="lp-workflow-company">f.</span><p className="lp-workflow-eyebrow">FIELDWORK STUDIO</p><h4>Senior Product<br />Designer</h4><p>London · Remote-friendly</p><div className="lp-workflow-rule" /><p className="lp-workflow-eyebrow">EXPERIENCE TO BRING FORWARD</p><div className="lp-workflow-fact"><Check size={14} /><span>User research</span></div><div className="lp-workflow-fact"><Check size={14} /><span>Design systems</span></div><span className="lp-workflow-small-note">Sample role & application</span></div>
        <div className="lp-workflow-letter lp-workflow-piece"><div className="lp-workflow-letter-top"><span><FileText size={15} /> Application draft</span><Tag quiet>For review</Tag></div><p className="lp-workflow-letter-greeting">Hello, Fieldwork team.</p><p>My approach to product design starts with understanding people.</p><p>Across five years of <mark className="lp-workflow-evidence">user research and design systems</mark> work, I have learned to turn complex problems into clear, useful experiences.</p><div className="lp-workflow-review-reminder"><PencilSimple size={15} /><span>A starting point.<br /><strong>Your words get the final say.</strong></span></div><a className="lp-workflow-review-link" href="#your-control">Try a sample review <ArrowRight size={16} /></a></div>
      </div>
    </article>
  );
}

function TrackingScene() {
  return (
    <article className="lp-workflow-scene" data-workflow-scene="4" aria-label="Step 5: Track the next step">
      <SceneHeading index={4} />
      <div className="lp-workflow-scene-grid">
        <Connector />
        <div className="lp-workflow-tracking-card lp-workflow-piece"><div className="lp-workflow-job-top"><span className="lp-workflow-company">f.</span><span>Fieldwork Studio<small>Sample application</small></span></div><h4>Senior Product<br />Designer</h4><div className="lp-workflow-approval"><CheckCircle size={17} weight="fill" /><span>Reviewed by you</span></div><p>Your application, with a clear place for what comes next.</p><div className="lp-workflow-source"><span className="lp-workflow-mini-avatar">MC</span> Your search. Your pace.</div></div>
        <div className="lp-workflow-tracking lp-workflow-piece"><p className="lp-workflow-eyebrow">YOUR APPLICATION JOURNEY</p><ol><li className="is-complete"><span className="lp-workflow-timeline-point"><Check size={12} /></span><div><h5>Application prepared</h5><p>Materials tailored to the role</p></div></li><li className="is-complete"><span className="lp-workflow-timeline-point"><Check size={12} /></span><div><h5>Reviewed by you</h5><p>Ready when you are</p></div></li><li className="is-next"><span className="lp-workflow-timeline-point" /><div><h5>Choose your next step</h5><p>Record progress or plan a follow-up</p></div></li><li><span className="lp-workflow-timeline-point" /><div><h5>Prepare for the conversation</h5><p>Practise when an interview is ahead</p></div></li></ol></div>
      </div>
    </article>
  );
}

export function WorkflowStory() {
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let disposed = false;
    let revert: (() => void) | undefined;
    let refreshFrame = 0;

    async function initialize() {
      const [{ gsap }, { ScrollTrigger }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger')]);
      if (disposed || !sectionRef.current) return;
      gsap.registerPlugin(ScrollTrigger);
      const section = sectionRef.current;
      const media = gsap.matchMedia();
      revert = () => media.revert();

      media.add('(min-width: 1000px) and (prefers-reduced-motion: no-preference)', () => {
        section.classList.add('is-animated');
        section.dataset.workflowMode = 'animated';
        const scenes = Array.from(section.querySelectorAll<HTMLElement>('[data-workflow-scene]'));
        const captions = Array.from(section.querySelectorAll<HTMLElement>('[data-workflow-caption]'));
        const steps = Array.from(section.querySelectorAll<HTMLElement>('[data-workflow-step]'));
        const fills = Array.from(section.querySelectorAll<HTMLElement>('[data-workflow-fill]'));
        const pin = section.querySelector<HTMLElement>('.lp-workflow-pin');
        const paths = Array.from(section.querySelectorAll<SVGPathElement>('.lp-workflow-connector-draw'));
        const focusable = scenes.flatMap((scene) => Array.from(scene.querySelectorAll<HTMLElement>('a, button')));
        const originalTabIndices = focusable.map((element) => element.getAttribute('tabindex'));
        const originalSceneState = scenes.map((scene) => ({ inert: scene.inert, ariaHidden: scene.getAttribute('aria-hidden') }));
        if (!pin) return;

        gsap.set(scenes, { opacity: 0, xPercent: 5, pointerEvents: 'none' });
        gsap.set(scenes[0], { opacity: 1, xPercent: 0, pointerEvents: 'auto' });
        gsap.set(captions, { opacity: 0, y: 12 });
        gsap.set(captions[0], { opacity: 1, y: 0 });
        gsap.set(fills, { scaleX: 0, transformOrigin: 'left center' });
        paths.forEach((path) => {
          const length = path.getTotalLength();
          gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });
        });

        let activeChapter = -1;
        const setChapter = (index: number) => {
          if (index === activeChapter) return;
          activeChapter = index;
          section.dataset.workflowChapter = String(index + 1);
          section.dataset.activeStep = String(index);
          steps.forEach((step, stepIndex) => step.classList.toggle('is-current', stepIndex === index));
          scenes.forEach((scene, sceneIndex) => {
            scene.inert = sceneIndex !== index;
            if (sceneIndex === index) scene.removeAttribute('aria-hidden');
            else scene.setAttribute('aria-hidden', 'true');
            scene.querySelectorAll<HTMLElement>('a, button').forEach((element) => {
              if (sceneIndex === index) element.removeAttribute('tabindex');
              else element.setAttribute('tabindex', '-1');
            });
          });
        };
        setChapter(0);

        // One reversible timeline controls the panels, evidence, paths, and chapter rail.
        const timeline = gsap.timeline({
          defaults: { ease: 'power2.inOut' },
          scrollTrigger: {
            id: 'jobpilot-workflow',
            trigger: pin,
            start: 'top 84px',
            end: () => `+=${Math.min(window.innerHeight * 3.2, 2900)}`,
            pin: true,
            scrub: 0.65,
            anticipatePin: 1,
            invalidateOnRefresh: true,
          },
        });

        scenes.forEach((scene, index) => {
          const at = index * 1.5;
          const pieces = scene.querySelectorAll('.lp-workflow-piece');
          timeline.addLabel(`chapter-${index + 1}`, at);
          if (index > 0) {
            timeline.to(scenes[index - 1], { opacity: 0, xPercent: -5, pointerEvents: 'none', duration: 0.3 }, at);
            timeline.to(captions[index - 1], { opacity: 0, y: -12, duration: 0.2 }, at);
            timeline.fromTo(scene, { opacity: 0, xPercent: 5, clipPath: 'inset(0 0 0 12%)' }, { opacity: 1, xPercent: 0, clipPath: 'inset(0 0 0 0%)', pointerEvents: 'auto', duration: 0.5 }, at + 0.1);
            timeline.to(captions[index], { opacity: 1, y: 0, duration: 0.4 }, at + 0.15);
            timeline.fromTo(pieces, { y: 16 }, { y: 0, stagger: 0.08, duration: 0.55 }, at + 0.1);
          }
          timeline.to(paths[index], { strokeDashoffset: 0, duration: 0.65 }, at + 0.2);
          timeline.fromTo(scene.querySelectorAll('.lp-workflow-evidence'), { backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%', duration: 0.6 }, at + 0.1);
          timeline.to(fills[index], { scaleX: 1, duration: 1.5, ease: 'none' }, at);
        });

        // Use rendered timeline time, including scrub smoothing and reverse playback.
        // Change the active scene midway through the short handover, when it is visible.
        timeline.eventCallback('onUpdate', () => {
          setChapter(Math.max(0, Math.min(4, Math.floor((timeline.time() - 0.25) / 1.5))));
        });

        return () => {
          section.classList.remove('is-animated');
          section.dataset.workflowMode = 'static';
          delete section.dataset.workflowChapter;
          delete section.dataset.activeStep;
          steps.forEach((step) => step.classList.remove('is-current'));
          scenes.forEach((scene, index) => {
            scene.inert = originalSceneState[index].inert;
            if (originalSceneState[index].ariaHidden === null) scene.removeAttribute('aria-hidden');
            else scene.setAttribute('aria-hidden', originalSceneState[index].ariaHidden!);
          });
          focusable.forEach((element, index) => {
            if (originalTabIndices[index] === null) element.removeAttribute('tabindex');
            else element.setAttribute('tabindex', originalTabIndices[index]!);
          });
        };
      });

      refreshFrame = requestAnimationFrame(() => ScrollTrigger.refresh());
      document.fonts?.ready.then(() => {
        if (!disposed) ScrollTrigger.refresh();
      });
    }

    void initialize().catch(() => {
      // The server-rendered, five-step story remains readable if motion cannot load.
      revert?.();
    });
    return () => {
      disposed = true;
      cancelAnimationFrame(refreshFrame);
      revert?.();
    };
  }, []);

  return (
    <section id="how-it-works" className="lp-workflow" ref={sectionRef} aria-labelledby="workflow-heading" data-workflow-mode="static">
      <div className="lp-workflow-inner">
        <div className="lp-workflow-section-label"><span>01 / A MORE THOUGHTFUL PROCESS</span><span>FROM EXPERIENCE TO OPPORTUNITY</span></div>
        <div className="lp-workflow-pin">
          <div className="lp-workflow-shell">
            <div className="lp-workflow-copy"><p className="lp-workflow-kicker">A SEARCH WITH DIRECTION</p><h2 id="workflow-heading">A little clarity.<br /><em>At every step.</em></h2><p className="lp-workflow-intro">Good opportunities start with understanding what you bring.</p><div className="lp-workflow-captions">{chapters.map((chapter, index) => <div className="lp-workflow-caption" data-workflow-caption={index} key={chapter.label}><span className="lp-workflow-chapter-number">0{index + 1} <span>/ 05</span></span><h3>{chapter.title}</h3><p>{chapter.copy}</p></div>)}</div><p className="lp-workflow-control-note"><span /> Prepared by AI. Directed by you.</p></div>
            <div className="lp-workflow-stage">
              <div className="lp-workflow-stage-top"><span className="lp-workflow-stage-brand"><span className="lp-workflow-brand-mark" aria-hidden="true">j.</span> Your next chapter</span><span className="lp-workflow-stage-owner"><span className="lp-workflow-mini-avatar">MC</span> Maya’s workspace</span></div>
              <div className="lp-workflow-scenes"><ExperienceScene /><ProfileScene /><OpportunitiesScene /><ReviewScene /><TrackingScene /></div>
              <div className="lp-workflow-stage-bottom"><span><span className="lp-workflow-status-dot" /> Your experience stays at the centre.</span><span>Illustrative product preview.</span></div>
            </div>
          </div>
          <ol className="lp-workflow-progress" aria-hidden="true">{chapters.map((chapter, index) => <li data-workflow-step={index} key={chapter.label}><span className="lp-workflow-progress-track"><span data-workflow-fill={index} /></span><span className="lp-workflow-progress-label"><span>0{index + 1}</span>{chapter.label}<ArrowRight size={14} /></span></li>)}</ol>
        </div>
      </div>
    </section>
  );
}
