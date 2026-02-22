import Link from 'next/link';

export default function HomePage() {
  return (
    <section className="space-y-6">
      <div className="rounded-2xl bg-white p-5 shadow">
        <h1 className="text-2xl font-bold">Kiểm kê AI VietJewelers</h1>
        <p className="mt-2 text-sm text-slate-600">
          Chụp ảnh khay trang sức, AI đếm tự động, nhân viên xác nhận và lưu kết quả.
        </p>
      </div>

      <div className="space-y-3">
        <Link href="/scan" className="block rounded-2xl bg-indigo-600 p-4 text-center font-semibold text-white">
          Kiểm kê mới
        </Link>
        <Link href="/history" className="block rounded-2xl bg-slate-900 p-4 text-center font-semibold text-white">
          Xem lịch sử
        </Link>
      </div>
    </section>
  );
}
