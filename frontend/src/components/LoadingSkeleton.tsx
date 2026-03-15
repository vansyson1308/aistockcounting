interface SkeletonProps {
  className?: string;
  count?: number;
}

function SkeletonLine({ className = '' }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-slate-200 dark:bg-slate-700 ${className}`}
    />
  );
}

export default function LoadingSkeleton({ className = '', count = 3 }: SkeletonProps) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl bg-white p-4 shadow dark:bg-slate-800">
          <SkeletonLine className="mb-2 h-4 w-3/4" />
          <SkeletonLine className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}
