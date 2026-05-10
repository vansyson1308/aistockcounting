import type { Metadata } from 'next';
import Link from 'next/link';

import DarkModeToggle from '@/components/DarkModeToggle';
import OfflineBanner from '@/components/OfflineBanner';
import RegisterSW from '@/components/RegisterSW';
import { GlobalToast } from '@/components/Toast';

import './globals.css';

export const metadata: Metadata = {
  title: 'VJ Inventory Truth Layer',
  description: 'Audit ton kho trang suc bang hinh anh',
  manifest: '/manifest.json',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
        <RegisterSW />
        <OfflineBanner />
        <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <nav className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
            <Link href="/" className="shrink-0 font-bold text-slate-900 dark:text-white">
              VJ Truth
            </Link>
            <div className="flex items-center gap-3 overflow-x-auto text-sm">
              <Link href="/scan" className="hover:text-indigo-600 dark:hover:text-indigo-400">
                Audit
              </Link>
              <Link href="/discrepancies" className="hover:text-indigo-600 dark:hover:text-indigo-400">
                Lech ton
              </Link>
              <Link href="/history" className="hover:text-indigo-600 dark:hover:text-indigo-400">
                Lich su
              </Link>
              <Link href="/stats" className="hover:text-indigo-600 dark:hover:text-indigo-400">
                Thong ke
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
