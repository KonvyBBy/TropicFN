import { useState } from "react";

export default function FilterSection() {
  const [searchValue, setSearchValue] = useState("");
  const [maxBudget, setMaxBudget] = useState("");
  const [daysOffline, setDaysOffline] = useState("0");
  const [minSkins, setMinSkins] = useState("");

  return (
    <section className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <i className="ri-search-line absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400 text-sm"></i>
            <input
              className="h-12 w-full rounded-xl border border-white/15 bg-black/35 pl-11 pr-4 text-sm text-white placeholder:text-zinc-400 transition focus-visible:shadow-focus"
              placeholder="Search accounts by skin, level, or keyword..."
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button className="inline-flex h-12 items-center justify-center rounded-xl px-5 text-sm font-medium transition focus-visible:shadow-focus disabled:opacity-50 bg-emerald-500 text-black hover:bg-emerald-400 active:scale-[0.99] whitespace-nowrap cursor-pointer">
              <i className="ri-shopping-cart-line mr-2"></i>
              Browse
            </button>
            <button className="inline-flex items-center justify-center rounded-xl px-4 text-sm font-medium transition focus-visible:shadow-focus disabled:opacity-50 border border-white/15 bg-white/5 text-white hover:border-white/30 hover:bg-white/10 h-12 gap-2 whitespace-nowrap cursor-pointer">
              <i className="ri-customer-service-line"></i>
              Help
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/20 p-3 sm:p-4">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
            Filter Options
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="space-y-1.5 text-xs text-zinc-400">
              <span className="flex items-center gap-1.5">
                <i className="ri-money-dollar-circle-line text-zinc-500"></i>
                Max Budget
              </span>
              <input
                className="h-11 w-full rounded-xl border border-white/15 bg-black/35 px-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                type="number"
                min={0}
                placeholder="No limit"
                value={maxBudget}
                onChange={(e) => setMaxBudget(e.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              <span className="flex items-center gap-1.5">
                <i className="ri-time-line text-zinc-500"></i>
                Days Offline
              </span>
              <input
                className="h-11 w-full rounded-xl border border-white/15 bg-black/35 px-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                type="number"
                min={0}
                placeholder="Any"
                value={daysOffline}
                onChange={(e) => setDaysOffline(e.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-xs text-zinc-400">
              <span className="flex items-center gap-1.5">
                <i className="ri-t-shirt-line text-zinc-500"></i>
                Minimum Skins
              </span>
              <input
                className="h-11 w-full rounded-xl border border-white/15 bg-black/35 px-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                type="number"
                min={0}
                placeholder="Any"
                value={minSkins}
                onChange={(e) => setMinSkins(e.target.value)}
              />
            </label>
          </div>
        </div>
      </div>
    </section>
  );
}