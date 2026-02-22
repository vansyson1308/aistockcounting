import type { Metadata } from 'next';
import Link from 'next/link';

import OfflineBanner from '@/components/OfflineBanner';

import './globals.css';

export const metadata: Metadata = {
  title: 'VJ Stock Counting',
  description: 'AI kiểm kê trang sức VietJewelers',
  manifest: '/manifest.json',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <OfflineBanner />
        <header className="sticky top-0 z-40 border-b bg-white/95 backdrop-blur">
          <nav className="mx-auto flex max-w-md items-center justify-between px-4 py-3">
            <Link href="/" className="font-bold text-slate-900">VJ Count</Link>
            <div className="flex gap-3 text-sm">
              <Link href="/scan">Kiểm kê</Link>
              <Link href="/history">Lịch sử</Link>
              <Link href="/stats">Thống kê</Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto min-h-screen w-full max-w-md px-4 py-4">{children}</main>
      </body>
    </html>
  );
}
