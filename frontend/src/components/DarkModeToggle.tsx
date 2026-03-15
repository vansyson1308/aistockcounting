'use client';

import { useEffect, useState } from 'react';

export default function DarkModeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('vjsc-dark');
    const isDark = stored === 'true';
    setDark(isDark);
    document.documentElement.classList.toggle('dark', isDark);
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('vjsc-dark', String(next));
    document.documentElement.classList.toggle('dark', next);
  };

  return (
    <button
      onClick={toggle}
      className="rounded-lg p-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-700"
      aria-label={dark ? 'Light mode' : 'Dark mode'}
    >
      {dark ? '\u2600\uFE0F' : '\uD83C\uDF19'}
    </button>
  );
}
