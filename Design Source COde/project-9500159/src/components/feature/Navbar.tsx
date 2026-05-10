import { Link, useLocation } from "react-router-dom";
import { useState, useEffect } from "react";

export default function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const isActive = (path: string) => location.pathname === path;

  return (
    <header
      className={`sticky top-3 z-30 mb-5 rounded-2xl px-2.5 py-2.5 sm:px-3 sm:py-3 md:top-4 md:mb-7 md:px-6 transition-all duration-300 ${
        isScrolled
          ? "bg-zinc-950/80 border border-white/10 backdrop-blur-xl"
          : "bg-transparent"
      }`}
    >
      <div className="flex items-center justify-between gap-2 sm:gap-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-6 lg:gap-8">
          <Link to="/" className="flex min-w-0 items-center gap-2.5 sm:gap-3">
            <img
              src="https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f"
              alt="Konvy Accounts"
              className="h-8 w-8 rounded-lg object-cover sm:h-9 sm:w-9"
            />
            <span className="hidden font-space text-lg font-bold text-white sm:inline">
              Konvy Accounts
            </span>
            <span className="truncate font-space text-[15px] font-bold text-white sm:hidden">
              Konvy
            </span>
          </Link>
          <nav className="hidden items-center gap-4 text-xs text-zinc-400 lg:flex lg:gap-5 lg:text-sm">
            <Link
              to="/"
              className={`transition hover:text-emerald-300 ${isActive("/") ? "text-emerald-400 font-medium" : ""}`}
            >
              Marketplace
            </Link>
            <Link
              to="/transactions"
              className={`transition hover:text-emerald-300 ${isActive("/transactions") ? "text-emerald-400 font-medium" : ""}`}
            >
              Transaction History
            </Link>
            <Link
              to="/my-accounts"
              className={`transition hover:text-emerald-300 ${isActive("/my-accounts") ? "text-emerald-400 font-medium" : ""}`}
            >
              My Accounts
            </Link>
            <Link
              to="/support"
              className={`transition hover:text-emerald-300 ${isActive("/support") ? "text-emerald-400 font-medium" : ""}`}
            >
              Support
            </Link>
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <Link to="/login">
            <button className="inline-flex items-center justify-center rounded-xl font-medium transition focus-visible:shadow-focus disabled:opacity-50 border border-white/15 bg-white/5 text-white hover:border-emerald-400/50 hover:text-emerald-300 h-8 px-2.5 text-[11px] sm:h-10 sm:px-3 sm:text-sm whitespace-nowrap cursor-pointer">
              Login
            </button>
          </Link>
          <Link to="/register">
            <button className="inline-flex items-center justify-center rounded-xl font-medium transition focus-visible:shadow-focus disabled:opacity-50 bg-emerald-500 text-black hover:bg-emerald-400 active:scale-[0.99] h-8 px-2.5 text-[11px] sm:h-10 sm:px-3 sm:text-sm whitespace-nowrap cursor-pointer">
              Register
            </button>
          </Link>
        </div>
      </div>

      <nav className="mt-3 flex items-center gap-2 overflow-x-auto pb-1 text-xs text-zinc-300 lg:hidden">
        <Link
          to="/"
          className={`whitespace-nowrap rounded-lg border border-white/15 px-3 py-1.5 transition ${isActive("/") ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-black/35 text-zinc-300 hover:text-white"}`}
        >
          Marketplace
        </Link>
        <Link
          to="/transactions"
          className={`whitespace-nowrap rounded-lg border border-white/15 px-3 py-1.5 transition ${isActive("/transactions") ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-black/35 text-zinc-300 hover:text-white"}`}
        >
          History
        </Link>
        <Link
          to="/my-accounts"
          className={`whitespace-nowrap rounded-lg border border-white/15 px-3 py-1.5 transition ${isActive("/my-accounts") ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-black/35 text-zinc-300 hover:text-white"}`}
        >
          My Accounts
        </Link>
        <Link
          to="/support"
          className={`whitespace-nowrap rounded-lg border border-white/15 px-3 py-1.5 transition ${isActive("/support") ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-black/35 text-zinc-300 hover:text-white"}`}
        >
          Support
        </Link>
      </nav>
    </header>
  );
}