'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { Archive, ArrowUpRight, Bell, Briefcase, CaretDown, ChartBar, Compass, FileText, GearSix, List, LockSimple, SignOut, SquaresFour, UserCircle } from '@phosphor-icons/react';
import { useAuth } from '../lib/auth';
import { EntitlementsProvider } from '../lib/entitlements';
import { DueReminders } from './Reminders';
import { Button } from './ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from './ui/dropdown-menu';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from './ui/sheet';

const groups = [
  { label: 'Workspace', items: [
    { href: '/jobs', label: 'Saved jobs', icon: SquaresFour },
    { href: '/discover', label: 'Discover jobs', icon: Compass },
    { href: '/applications', label: 'Applications', icon: Briefcase },
    { href: '/reminders', label: 'Reminders', icon: Bell },
    { href: '/insights', label: 'Insights', icon: ChartBar },
  ] },
  { label: 'Your toolkit', items: [
    { href: '/resumes', label: 'Resumes', icon: FileText },
    { href: '/profile', label: 'Profile', icon: UserCircle },
  ] },
  { label: 'Manage', items: [
    { href: '/archive', label: 'Archive', icon: Archive },
    { href: '/settings', label: 'Settings', icon: GearSix },
  ] },
];
function Navigation({ path, onNavigate }: { path: string; onNavigate?: () => void }) {
  return <nav className="workspace-nav" aria-label="Primary">{groups.map(group => <div className="nav-group" key={group.label}>
    <p className="nav-group-label">{group.label}</p>
    {group.items.map(({ href, label, icon: Icon }) => {
      const active = path === href || path.startsWith(`${href}/`);
      return <Link href={href} key={href} onClick={onNavigate} aria-current={active ? 'page' : undefined} className={`workspace-nav-link${active ? ' is-active' : ''}`}><Icon size={20} weight={active ? 'fill' : 'regular'} aria-hidden="true" /><span>{label}</span>{active && <span className="nav-active-dot" aria-hidden="true" />}</Link>;
    })}
  </div>)}</nav>;
}
export function Shell({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const path = usePathname();
  const [menu, setMenu] = useState(false);
  if (loading || !user) return <main className="center-state" role="status"><Compass size={36} className="opening-mark" aria-hidden="true" /><p>Opening your journal…</p></main>;
  const name = user.email.split('@')[0];
  const initials = name.slice(0, 2).toUpperCase();
  const current = groups.flatMap(group => group.items).find(item => path === item.href || path.startsWith(`${item.href}/`));
  return <div className="workspace-shell"><a className="skip-link" href="#main">Skip to content</a>
    <aside className="workspace-sidebar">
      <Link className="workspace-brand" href="/jobs"><span className="brand-mark"><Compass size={27} weight="duotone" aria-hidden="true" /></span><span>JobPilot<span className="brand-ai">AI</span><small>Your next chapter.</small></span></Link>
      <Navigation path={path} />
      <div className="sidebar-footer"><div className="sidebar-note"><span className="sidebar-note-icon"><Compass size={21} aria-hidden="true" /></span><p>A little direction.<br /><strong>A world of possibility.</strong></p><Link href="/discover">Explore opportunities <ArrowUpRight size={15} aria-hidden="true" /></Link></div><p className="sidebar-privacy"><LockSimple size={13} aria-hidden="true" />Your private career workspace</p></div>
    </aside>
    <div className="workspace-body"><header className="workspace-topbar">
      <Button variant="ghost" size="icon" className="mobile-nav-toggle" aria-label="Open navigation" onClick={() => setMenu(true)}><List size={22} /></Button>
      <div className="workspace-breadcrumb"><span>My workspace</span><span aria-hidden="true">/</span><strong>{current?.label || 'Getting started'}</strong></div>
      <div className="topbar-actions"><DueReminders /><DropdownMenu>
        <DropdownMenuTrigger asChild><button type="button" className="account-toggle workspace-account" aria-label={`Account menu for ${user.email}`}><span className="workspace-avatar">{initials}</span><span className="workspace-account-name">{name}</span><CaretDown size={13} aria-hidden="true" /></button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64"><DropdownMenuLabel className="font-normal"><span className="block truncate text-sm font-medium">{user.email}</span><span className="block text-xs text-muted-foreground">Your private career journal</span></DropdownMenuLabel><DropdownMenuSeparator /><DropdownMenuItem asChild><Link href="/profile"><UserCircle size={17} aria-hidden="true" />My profile</Link></DropdownMenuItem><DropdownMenuItem asChild><Link href="/settings"><GearSix size={17} aria-hidden="true" />Account settings</Link></DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem onSelect={() => { void signOut(); }}><SignOut size={17} aria-hidden="true" />Log out</DropdownMenuItem></DropdownMenuContent>
      </DropdownMenu></div>
    </header><main id="main" className="workspace-main" tabIndex={-1}>
      {user.onboarding_step && user.onboarding_step !== 'done' && <div className="onboarding-notice"><span>Let’s get your workspace ready.</span><Link href="/onboarding">Continue setup <ArrowUpRight size={15} aria-hidden="true" /></Link></div>}
      <EntitlementsProvider>{children}</EntitlementsProvider>
    </main><footer className="workspace-footer"><span>JobPilot AI</span><span>A thoughtful next step.</span><LockSimple size={12} aria-hidden="true" /></footer></div>
    <Sheet open={menu} onOpenChange={setMenu}><SheetContent side="left" className="workspace-mobile-sheet"><SheetHeader><SheetTitle><span className="mobile-brand"><Compass size={25} weight="duotone" aria-hidden="true" />JobPilot AI</span></SheetTitle><SheetDescription>Your private career workspace</SheetDescription></SheetHeader><Navigation path={path} onNavigate={() => setMenu(false)} /></SheetContent></Sheet>
  </div>;
}
