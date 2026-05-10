import { Link } from "react-router-dom";

export default function HeroSection() {
  return (
    <header className="glass-panel relative overflow-hidden rounded-3xl px-5 py-8 sm:px-8 sm:py-10 md:px-10 md:py-12">
      {/* Subtle corner accent */}
      <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-emerald-500/5 blur-[80px]"></div>
      <div className="absolute -bottom-20 -left-20 h-40 w-40 rounded-full bg-white/[0.02] blur-[60px]"></div>

      <div className="relative z-10 max-w-2xl">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span className="text-[11px] font-medium text-emerald-300">
            Live marketplace — 12 accounts listed today
          </span>
        </div>

        <h1 className="font-space text-3xl font-bold leading-tight text-white sm:text-4xl md:text-5xl">
          Premium Fortnite
          <span className="block text-emerald-400">Account Marketplace</span>
        </h1>

        <p className="mt-4 max-w-lg text-sm leading-relaxed text-zinc-400 sm:text-base">
          Browse verified accounts with rare skins, high levels, and stacked inventories. Instant delivery with balance payments.
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/register">
            <button className="inline-flex h-11 items-center justify-center rounded-xl px-5 text-sm font-medium transition bg-emerald-500 text-black hover:bg-emerald-400 active:scale-[0.99] whitespace-nowrap cursor-pointer">
              Get Started
              <i className="ri-arrow-right-line ml-2"></i>
            </button>
          </Link>
          <button className="inline-flex h-11 items-center justify-center rounded-xl border border-white/15 bg-white/5 px-5 text-sm font-medium text-zinc-300 transition hover:border-white/30 hover:text-white whitespace-nowrap cursor-pointer">
            Learn More
          </button>
        </div>
      </div>
    </header>
  );
}