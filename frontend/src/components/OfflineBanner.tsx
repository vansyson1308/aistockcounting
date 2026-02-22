'use client';

import { useEffect, useState } from 'react';

export default function OfflineBanner() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    setOnline(navigator.onLine);
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  if (online) return null;
  return <div className="bg-amber-100 px-4 py-2 text-center text-sm text-amber-800">Bạn đang offline.</div>;
}
