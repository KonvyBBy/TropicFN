import { useState } from "react";

const currencies = ["EUR", "USD", "GBP", "PLN", "CZK"];

interface HeaderProps {
  onMenuToggle: () => void;
  searchQuery: string;
  onSearchChange: (val: string) => void;
}

export default function Header({ onMenuToggle, searchQuery, onSearchChange }: HeaderProps) {
  const [currency, setCurrency] = useState("EUR");
  const [showCurrencyMenu, setShowCurrencyMenu] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-card/95 backdrop-blur-md border-b border-border">
      <div className="mx-auto px-4 py-3 flex items-center gap-3">
        {/* Mobile filter toggle */}
        <button
          className="lg:hidden p-2 rounded-lg bg-secondary hover:bg-card-hover border border-border transition-colors cursor-pointer"
          aria-label="Filters"
          onClick={onMenuToggle}
        >
          <i className="ri-equalizer-2-line text-foreground text-sm w-4 h-4 flex items-center justify-center" />
        </button>

        {/* Logo - styled text wordmark matching the AccountX brand */}
        <a href="/" className="flex items-center gap-2.5 shrink-0 cursor-pointer no-underline">
          <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/40 flex items-center justify-center shrink-0">
            <span className="font-display text-lg font-extrabold text-primary text-glow leading-none">X</span>
          </div>
          <div className="hidden sm:flex flex-col leading-none gap-0.5">
            <span className="font-display text-xl font-extrabold tracking-widest leading-none">
              <span className="text-foreground">ACCOUNT</span>
              <span className="text-primary text-glow">X</span>
            </span>
            <span className="text-[8px] text-muted-foreground tracking-[0.2em] uppercase font-semibold">Fortnite Shop</span>
          </div>
        </a>

        {/* Search */}
        <div className="flex-1 max-w-2xl relative">
          <i className="ri-search-2-line absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm w-4 h-4 flex items-center justify-center" />
          <input
            placeholder="Search accounts by skins, V-Bucks, level..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full h-10 pl-9 pr-3 rounded-xl bg-secondary border border-border text-sm font-medium text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary/50 transition-all"
          />
        </div>

        {/* Nav links desktop */}
        <div className="hidden md:flex items-center gap-1">
          <a href="/" className="px-3 py-1.5 rounded-lg text-xs font-semibold text-secondary-foreground hover:text-foreground hover:bg-secondary transition-colors cursor-pointer whitespace-nowrap no-underline">
            Buy Account
          </a>
          <a href="/" className="px-3 py-1.5 rounded-lg text-xs font-semibold text-secondary-foreground hover:text-foreground hover:bg-secondary transition-colors cursor-pointer whitespace-nowrap no-underline">
            Sell Account
          </a>
        </div>

        {/* Currency selector */}
        <div className="relative">
          <button
            className="flex items-center gap-1.5 px-2.5 py-2 rounded-xl bg-secondary border border-border text-xs font-semibold text-foreground hover:bg-card-hover transition-colors whitespace-nowrap cursor-pointer"
            onClick={() => setShowCurrencyMenu((v) => !v)}
          >
            <i className="ri-money-dollar-circle-line text-primary w-3.5 h-3.5 flex items-center justify-center" />
            <span className="hidden sm:inline">{currency}</span>
            <i className="ri-arrow-down-s-line text-muted-foreground w-3 h-3 flex items-center justify-center" />
          </button>
          {showCurrencyMenu && (
            <div className="absolute right-0 top-full mt-1.5 w-28 bg-card border border-border rounded-xl overflow-hidden z-50">
              {currencies.map((c) => (
                <button
                  key={c}
                  className={`w-full text-left px-3 py-2 text-xs font-semibold transition-colors hover:bg-secondary cursor-pointer ${
                    c === currency ? "text-primary" : "text-foreground"
                  }`}
                  onClick={() => { setCurrency(c); setShowCurrencyMenu(false); }}
                >
                  {c}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Sign In */}
        <button className="flex items-center gap-1.5 px-4 py-2 rounded-xl gradient-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-opacity whitespace-nowrap cursor-pointer uppercase tracking-wider">
          <i className="ri-user-line w-3.5 h-3.5 flex items-center justify-center" />
          <span className="hidden sm:inline">Sign In</span>
        </button>
      </div>
    </header>
  );
}