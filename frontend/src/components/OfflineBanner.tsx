'use client';

import { useEffect, useState } from 'react';
import { flush, getPendingCount } from '@/lib/offline-queue';

export default function OfflineBanner() {
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    setOnline(navigator.onLine);

    const goOnline = async () => {
      setOnline(true);
      const synced = await flush();
      if (synced > 0) setPending((p) => Math.max(0, p - synced));
    };
    const goOffline = () => setOnline(false);

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);

    const interval = setInterval(async () => {
      setPending(await getPendingCount());
    }, 5000);

    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
      clearInterval(interval);
    };
  }, []);

  if (online && pending === 0) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500 px-4 py-2 text-center text-sm font-medium text-white">
      {!online
        ? `Bạn đang offline. ${pending > 0 ? `${pending} bản ghi chờ đồng bộ.` : ''}`
        : `Đang đồng bộ ${pending} bản ghi...`}
    </div>
  );
}
