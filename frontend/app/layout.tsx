import '@fontsource-variable/newsreader';
import '@fontsource-variable/dm-sans';
import './globals.css';
import { AuthProvider } from '../lib/auth';

export const metadata = { title: 'JobPilot AI', description: 'Your private career journal' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body><AuthProvider>{children}</AuthProvider></body></html>;
}
