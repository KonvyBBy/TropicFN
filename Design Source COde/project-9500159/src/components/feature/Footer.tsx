import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="mt-12 border-t border-white/5 bg-zinc-950/60 py-8 sm:py-10">
      <div className="mx-auto max-w-[1300px] px-3 sm:px-4 md:px-8">
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <img
                src="https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f"
                alt="Konvy Accounts"
                className="h-7 w-7 rounded-lg object-cover"
              />
              <span className="font-space text-sm font-semibold text-white">
                Konvy Accounts
              </span>
            </div>
            <p className="text-xs text-zinc-500 leading-relaxed">
              Premium Fortnite account marketplace. Secure payments, instant delivery, verified sellers.
            </p>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">Platform</h3>
            <nav className="flex flex-col gap-2 text-xs text-zinc-500">
              <Link to="/" className="transition hover:text-emerald-400">Marketplace</Link>
              <Link to="/transactions" className="transition hover:text-emerald-400">Transaction History</Link>
              <Link to="/my-accounts" className="transition hover:text-emerald-400">My Accounts</Link>
            </nav>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">Company</h3>
            <nav className="flex flex-col gap-2 text-xs text-zinc-500">
              <Link to="/support" className="transition hover:text-emerald-400">Support</Link>
              <Link to="/warranty" className="transition hover:text-emerald-400">Warranty</Link>
              <Link to="/terms" className="transition hover:text-emerald-400">Terms of Service</Link>
            </nav>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">Legal</h3>
            <nav className="flex flex-col gap-2 text-xs text-zinc-500">
              <Link to="/terms" className="transition hover:text-emerald-400">Terms of Service</Link>
              <Link to="/warranty" className="transition hover:text-emerald-400">Warranty Policy</Link>
              <span className="text-zinc-600">support@konvyaccounts.com</span>
            </nav>
          </div>
        </div>

        <div className="mt-8 border-t border-white/5 pt-6 text-center text-xs text-zinc-600">
          &copy; {new Date().getFullYear()} Konvy Accounts. All rights reserved.
        </div>
      </div>
    </footer>
  );
}