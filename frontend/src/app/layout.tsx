import type { Metadata } from 'next';
import Link from 'next/link';

import DarkModeToggle from '@/components/DarkModeToggle';
import OfflineBanner from '@/components/OfflineBanner';
import RegisterSW from '@/components/RegisterSW';
import { GlobalToast } from '@/components/Toast';

import './globals.css';

export const metadata: Metadata = {
  title: 'VJ Stock Counting',
  description: 'AI kiểm kê trang sức VietJewelers',
  manifest: '/manifest.json',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
        <RegisterSW />
        <OfflineBanner />
        <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <nav className="mx-auto flex max-w-md items-center justify-between px-4 py-3 sm:max-w-lg md:max-w-xl lg:max-w-2xl">
            <Link href="/" className="font-bold text-slate-900 dark:text-white">VJ Count</Link>
            <div className="flex items-center gap-3 text-sm">
              <Link href="/scan" className="hover:text-indigo-600 dark:hover:text-indigo-400">Kiểm kê</Link>
              <Link href="/history" className="hover:text-indigo-600 dark:hover:text-indigo-400">Lịch sử</Link>
              <Link href="/stats" className="hover:text-indigo-600 dark:hover:text-indigo-400">Thống kê</Link>
              <DarkModeToggle />
            </div>
          </nav>
        </header>
        <main className="mx-auto min-h-screen w-full max-w-md px-4 py-4 sm:max-w-lg md:max-w-xl lg:max-w-2xl">{children}</main>
        <GlobalToast />
      </body>
    </html>
  );
}
