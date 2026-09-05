import type { Metadata } from 'next';
import './globals.css';
import { Providers } from './providers';

export const metadata: Metadata = {
  title: 'Lenny Growth Assistant | Claude-Style AI Workspace',
  description:
    'Forward Deployed AI Assistant for Lenny’s Podcast transcripts, RAG queries, and Ship30 essay generation.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <body className="h-full bg-surface-base text-slate-100 antialiased selection:bg-amber-500/30 selection:text-amber-200">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
