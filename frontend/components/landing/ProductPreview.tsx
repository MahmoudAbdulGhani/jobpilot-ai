'use client';

import { useState, type CSSProperties } from 'react';
import { ArrowRight, ArrowUpRight, Check, FileText, MapPin, Sparkle } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import './preview.css';

type SampleJob = {
  company: string;
  monogram: string;
  title: string;
  location: string;
  working: string;
  skills: string[];
  description: string;
};

const samples = {
  design: {
    label: 'Product design',
    headline: 'Product designer',
    experience: '5 years of thoughtful digital work',
    skills: ['Product strategy', 'Figma', 'Research'],
    jobs: [
      { company: 'Northstar Studio', monogram: 'N', title: 'Senior Product Designer', location: 'London, UK', working: 'Remote in Europe', skills: ['Product strategy', 'Figma', 'Research'], description: 'Help a small product team make everyday decisions feel simpler.' },
      { company: 'Forma', monogram: 'f', title: 'Product Designer', location: 'Amsterdam, NL', working: 'Hybrid', skills: ['Figma', 'Design systems'], description: 'Bring a connected design language to tools for creative teams.' },
    ],
  },
  engineering: {
    label: 'Engineering',
    headline: 'Frontend engineer',
    experience: '5 years building useful web experiences',
    skills: ['React', 'TypeScript', 'Accessibility'],
    jobs: [
      { company: 'Fieldwork', monogram: 'F', title: 'Senior Frontend Engineer', location: 'Berlin, DE', working: 'Remote in Europe', skills: ['React', 'TypeScript', 'Accessibility'], description: 'Build clear, accessible software for people doing meaningful work.' },
      { company: 'Common Ground', monogram: 'c', title: 'Product Engineer', location: 'Paris, FR', working: 'Hybrid', skills: ['TypeScript', 'Web performance'], description: 'Work across design and engineering on a collaborative workspace.' },
    ],
  },
  marketing: {
    label: 'Marketing',
    headline: 'Content strategist',
    experience: '5 years connecting products and people',
    skills: ['Content strategy', 'SEO', 'Analytics'],
    jobs: [
      { company: 'Good Measure', monogram: 'g', title: 'Content Marketing Lead', location: 'Dublin, IE', working: 'Remote in Europe', skills: ['Content strategy', 'SEO', 'Analytics'], description: 'Shape the stories that help an independent product find its people.' },
      { company: 'Aperture', monogram: 'A', title: 'Brand Strategist', location: 'Copenhagen, DK', working: 'Hybrid', skills: ['Content strategy', 'Campaigns'], description: 'Turn a considered brand point of view into work that connects.' },
    ],
  },
} satisfies Record<string, { label: string; headline: string; experience: string; skills: string[]; jobs: SampleJob[] }>;

type Role = keyof typeof samples;

function ApplicationPreview({ job, role }: { job: SampleJob; role: Role }) {
  const profile = samples[role];

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button className="lp-job-preview-button" variant="ghost" aria-label={`Preview application for ${job.title} at ${job.company}`}>
          Preview application <ArrowUpRight aria-hidden="true" size={17} />
        </Button>
      </DialogTrigger>
      <DialogContent className="lp-preview-dialog">
        <DialogHeader className="lp-preview-dialog-header">
          <span className="lp-demo-kicker">YOUR APPLICATION, CONSIDERED</span>
          <DialogTitle className="lp-preview-dialog-title">A starting point. Make it yours.</DialogTitle>
          <DialogDescription className="lp-preview-dialog-description">
            {job.title} · {job.company}. Illustrative product preview.
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="cv" className="lp-application-tabs">
          <TabsList className="lp-application-tab-list" aria-label="Application documents">
            <TabsTrigger className="lp-application-tab" value="cv">CV</TabsTrigger>
            <TabsTrigger className="lp-application-tab" value="letter">Cover letter</TabsTrigger>
            <TabsTrigger className="lp-application-tab" value="email">Email preview</TabsTrigger>
          </TabsList>
          <TabsContent value="cv" className="lp-application-paper">
            <div className="lp-paper-topline"><span>CURRICULUM VITAE</span><FileText size={20} aria-hidden="true" /></div>
            <h3>Alex Morgan</h3>
            <p className="lp-paper-role">{profile.headline}</p>
            <h4>Profile</h4>
            <p>{profile.experience}. A collaborative, curious approach to creating useful experiences, with a focus on {profile.skills.slice(0, 2).join(' and ').toLowerCase()}.</p>
            <h4>Relevant experience</h4>
            <p>Partnered with a cross-functional team to turn research and customer needs into practical product improvements.</p>
            <div className="lp-paper-skill-list">{profile.skills.map(skill => <span key={skill}>{skill}</span>)}</div>
          </TabsContent>
          <TabsContent value="letter" className="lp-application-paper">
            <div className="lp-paper-topline"><span>COVER LETTER</span><FileText size={20} aria-hidden="true" /></div>
            <h3>A thoughtful introduction.</h3>
            <p>Dear {job.company} team,</p>
            <p>I am interested in the {job.title} role. Your focus on useful, considered work connects with the way I approach my own.</p>
            <p>My experience in {profile.skills[0].toLowerCase()} and {profile.skills[1]} would be a starting point for contributing to your team. I would welcome the opportunity to share a few relevant projects.</p>
            <p>Best,<br />Alex Morgan</p>
          </TabsContent>
          <TabsContent value="email" className="lp-application-paper">
            <div className="lp-paper-topline"><span>EMAIL DRAFT</span><FileText size={20} aria-hidden="true" /></div>
            <dl className="lp-email-details"><div><dt>To</dt><dd>Hiring team at {job.company}</dd></div><div><dt>Subject</dt><dd>Application · {job.title}</dd></div></dl>
            <p>Hello {job.company} team,</p>
            <p>I would love to be considered for your {job.title} opening. My CV and a short introduction would be attached for your review.</p>
            <p>Thank you for your time,<br />Alex Morgan</p>
            <span className="lp-email-attachment"><FileText size={16} aria-hidden="true" /> Alex_Morgan_CV.pdf · Example attachment</span>
          </TabsContent>
        </Tabs>
        <p className="lp-dialog-footnote"><Check size={17} aria-hidden="true" /> Sample content only. Nothing is saved or sent.</p>
      </DialogContent>
    </Dialog>
  );
}

export function ProductPreview() {
  const [role, setRole] = useState<Role>('design');
  const current = samples[role];

  return (
    <section id="product-preview" className="lp-product-section" aria-labelledby="lp-product-heading">
      <div className="lp-demo-container">
        <div className="lp-product-intro">
          <div>
            <p className="lp-demo-kicker">A FEEL FOR WHAT’S NEXT</p>
            <h2 id="lp-product-heading">Find your kind<br />of opportunity.</h2>
          </div>
          <p>Start with what matters to you.<br className="lp-demo-desktop-break" /> See how a few preferences become<br className="lp-demo-desktop-break" /> a more considered shortlist.</p>
        </div>

        <Tabs value={role} onValueChange={value => setRole(value as Role)} className="lp-workspace-tabs">
          <div className="lp-workspace-toolbar">
            <span className="lp-demo-preference-label">Explore a direction</span>
            <TabsList className="lp-role-tabs" aria-label="Sample role preference">
              {(Object.keys(samples) as Role[]).map(key => (
                <TabsTrigger className="lp-role-tab" key={key} value={key}>{samples[key].label}</TabsTrigger>
              ))}
            </TabsList>
            <span className="lp-workspace-demo-label"><span aria-hidden="true" /> LIVE LOCAL DEMO</span>
          </div>

          {(Object.keys(samples) as Role[]).map(key => (
            <TabsContent className="lp-workspace-panel" key={key} value={key}>
              <div className="lp-demo-workspace">
                <aside className="lp-demo-profile" aria-label="Sample candidate profile">
                  <div className="lp-demo-profile-mark" aria-hidden="true">am<span /></div>
                  <p className="lp-demo-profile-name">Alex Morgan</p>
                  <p className="lp-demo-profile-role">{current.headline}</p>
                  <div className="lp-demo-profile-divider" />
                  <span className="lp-demo-small-label">YOUR DIRECTION</span>
                  <p className="lp-demo-direction">Meaningful work.<br />Room to grow.</p>
                  <span className="lp-demo-small-label">EXPERIENCE TO BUILD ON</span>
                  <ul className="lp-demo-profile-skills">{current.skills.map(skill => <li key={skill}><Check size={14} aria-hidden="true" />{skill}</li>)}</ul>
                  <div className="lp-demo-profile-note"><Sparkle size={19} aria-hidden="true" /><p>Your experience is<br />the starting point.</p></div>
                </aside>

                <div className="lp-demo-results">
                  <div className="lp-demo-results-heading"><div><span className="lp-demo-small-label">THE SHORTLIST</span><h3>Possibilities, with context.</h3></div><span className="lp-demo-result-count">02 sample roles</span></div>
                  <div className="lp-demo-job-list">
                    {current.jobs.map((job, index) => (
                      <article key={job.company} className="lp-demo-job" style={{ '--lp-job-index': index } as CSSProperties}>
                        <div className="lp-demo-job-top"><span className={`lp-company-monogram lp-company-monogram-${index}`} aria-hidden="true">{job.monogram}</span><div><p className="lp-demo-company">{job.company}</p><h4>{job.title}</h4></div></div>
                        <p className="lp-demo-job-location"><span><MapPin size={14} aria-hidden="true" />{job.location}</span><span>{job.working}</span></p>
                        <p className="lp-demo-job-description">{job.description}</p>
                        <div className="lp-demo-job-bottom"><div className="lp-demo-job-skills" aria-label="Skills in common">{job.skills.map(skill => <span key={skill}>{skill}</span>)}</div><ApplicationPreview job={job} role={role} /></div>
                      </article>
                    ))}
                  </div>
                  <div className="lp-demo-workspace-footer"><span><Check size={15} aria-hidden="true" /> Context for your next decision.</span><ArrowRight size={18} aria-hidden="true" /></div>
                </div>
              </div>
            </TabsContent>
          ))}
        </Tabs>
        <p className="lp-demo-caption">Illustrative product preview. People, companies, and roles are fictional.</p>
        <span className="lp-demo-sr-only" role="status" aria-live="polite">Showing 2 sample {current.label.toLowerCase()} roles.</span>
      </div>
    </section>
  );
}
