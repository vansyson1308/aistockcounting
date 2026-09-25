import type { Metadata } from 'next';
import Link from 'next/link';

import DarkModeToggle from '@/components/DarkModeToggle';
import OfflineBanner from '@/components/OfflineBanner';
import RegisterSW from '@/components/RegisterSW';
import { GlobalToast } from '@/components/Toast';

import './globals.css';

export const metadata: Metadata = {
  title: 'VJ Inventory Truth Layer',
  description: 'TrayAgent: verified jewelry tray counts from a phone photo',
  manifest: '/manifest.json',
};

const navLinkClass =
  'shrink-0 whitespace-nowrap rounded px-1 py-1 hover:text-indigo-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 dark:hover:text-indigo-400';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
        <RegisterSW />
        <OfflineBanner />
        <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <nav
            aria-label="Main"
            className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3"
          >
            <Link href="/" className="shrink-0 font-bold text-slate-900 dark:text-white">
              VJ Truth
            </Link>
            <div className="flex items-center gap-3 overflow-x-auto text-sm">
              <Link href="/scan" className={navLinkClass}>
                Scan
              </Link>
              <Link href="/review" className={navLinkClass}>
                Review queue
              </Link>
              <Link href="/discrepancies" className={navLinkClass}>
                Discrepancies
              </Link>
              <Link href="/history" className={navLinkClass}>
                History
              </Link>
              <Link href="/stats" className={navLinkClass}>
                Stats
              </Link>
              <DarkModeToggle />
            </div>
          </nav>
        </header>
        <main className="mx-auto min-h-screen w-full max-w-5xl px-4 py-5">{children}</main>
        <GlobalToast />
      </body>
    </html>
  );
}
