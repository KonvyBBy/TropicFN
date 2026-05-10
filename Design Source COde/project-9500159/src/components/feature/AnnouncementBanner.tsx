export default function AnnouncementBanner() {
  return (
    <section className="flex items-center gap-3 rounded-2xl border border-emerald-500/15 bg-emerald-950/20 px-4 py-3 sm:px-5 sm:py-3.5">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15">
        <i className="ri-megaphone-line text-xs text-emerald-400"></i>
      </span>
      <p className="text-sm text-emerald-100">
        <span className="font-semibold text-emerald-300">NEW ACCOUNTS DAILY</span>{" "}
        <span className="text-emerald-100/70">— check back every day for fresh verified listings</span>
      </p>
    </section>
  );
}