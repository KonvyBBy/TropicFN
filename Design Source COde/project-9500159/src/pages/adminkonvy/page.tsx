import { useState } from "react";

export default function AdminPanel() {
  const [password, setPassword] = useState("");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [error, setError] = useState(false);

  const handleLogin = () => {
    if (password === "Kelvilo40") {
      setIsAuthenticated(true);
      setError(false);
    } else {
      setError(true);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center px-4">
        <div className="w-full max-w-sm">
          <div className="glass-panel rounded-3xl p-6 sm:p-8">
            <div className="mb-6 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                <i className="ri-shield-keyhole-line text-2xl text-emerald-400"></i>
              </div>
              <h1 className="font-space text-xl font-bold text-white sm:text-2xl">
                Admin Access
              </h1>
              <p className="mt-2 text-sm text-zinc-400">
                Enter the admin password to continue
              </p>
            </div>

            <div className="space-y-4">
              <div className="relative">
                <i className="ri-lock-password-line absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 text-sm"></i>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleLogin();
                  }}
                  placeholder="Enter password"
                  className={`h-12 w-full rounded-xl border bg-black/35 pl-11 pr-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus ${
                    error ? "border-red-500/50" : "border-white/15"
                  }`}
                />
              </div>
              {error && (
                <p className="text-xs text-red-400">Incorrect password. Please try again.</p>
              )}
              <button
                onClick={handleLogin}
                className="inline-flex h-12 w-full items-center justify-center rounded-xl px-4 text-sm font-medium transition focus-visible:shadow-focus disabled:opacity-50 bg-emerald-500 text-black hover:bg-emerald-400 active:scale-[0.99] whitespace-nowrap cursor-pointer"
              >
                Access Panel
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const stats = [
    { label: "Total Users", value: "1,247", icon: "ri-user-3-line", change: "+12%" },
    { label: "Total Sales", value: "$89,420", icon: "ri-money-dollar-circle-line", change: "+8%" },
    { label: "Active Listings", value: "342", icon: "ri-store-2-line", change: "+5%" },
    { label: "Pending Tickets", value: "7", icon: "ri-customer-service-line", change: "-2" },
  ];

  const recentTransactions = [
    { id: "#TXN-4821", buyer: "johndoe99", item: "OG Renegade Raider", amount: "$449", status: "Completed", time: "2 min ago" },
    { id: "#TXN-4820", buyer: "fortfan22", item: "Galaxy Skin Account", amount: "$189", status: "Pending", time: "5 min ago" },
    { id: "#TXN-4819", buyer: "stackedboy", item: "Black Knight + 250 Skins", amount: "$249", status: "Completed", time: "12 min ago" },
    { id: "#TXN-4818", buyer: "newbieFN", item: "Ghoul Trooper Starter", amount: "$159", status: "Completed", time: "18 min ago" },
    { id: "#TXN-4817", buyer: "proplayer", item: "Aerial Assault Trooper", amount: "$329", status: "Disputed", time: "34 min ago" },
  ];

  return (
    <div className="space-y-6 sm:space-y-8">
      <div className="flex items-center justify-between">
        <header>
          <h1 className="font-space text-2xl font-bold text-white sm:text-3xl">Admin Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-400">Overview of platform activity</p>
        </header>
        <button
          onClick={() => {
            setIsAuthenticated(false);
            setPassword("");
          }}
          className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-300 transition hover:border-white/30 hover:text-white cursor-pointer"
        >
          <i className="ri-logout-box-r-line"></i>
          Logout
        </button>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                <i className={`${stat.icon} text-emerald-400`}></i>
              </div>
              <span className="rounded-lg bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-400">
                {stat.change}
              </span>
            </div>
            <p className="mt-3 text-2xl font-bold text-white">{stat.value}</p>
            <p className="text-xs text-zinc-500">{stat.label}</p>
          </div>
        ))}
      </section>

      <section className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-space text-lg font-semibold text-white">Recent Transactions</h2>
          <button className="text-xs text-emerald-400 hover:text-emerald-300 transition cursor-pointer">
            View All
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs text-zinc-500">
                <th className="pb-3 pr-4 font-medium">Transaction ID</th>
                <th className="pb-3 pr-4 font-medium">Buyer</th>
                <th className="pb-3 pr-4 font-medium">Item</th>
                <th className="pb-3 pr-4 font-medium">Amount</th>
                <th className="pb-3 pr-4 font-medium">Status</th>
                <th className="pb-3 font-medium">Time</th>
              </tr>
            </thead>
            <tbody className="text-zinc-400">
              {recentTransactions.map((tx) => (
                <tr key={tx.id} className="border-b border-white/5 last:border-0">
                  <td className="py-3 pr-4 text-xs font-mono text-zinc-500">{tx.id}</td>
                  <td className="py-3 pr-4 text-white">{tx.buyer}</td>
                  <td className="py-3 pr-4">{tx.item}</td>
                  <td className="py-3 pr-4 font-medium text-white">{tx.amount}</td>
                  <td className="py-3 pr-4">
                    <span
                      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${
                        tx.status === "Completed"
                          ? "bg-emerald-500/10 text-emerald-400"
                          : tx.status === "Pending"
                          ? "bg-amber-500/10 text-amber-400"
                          : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {tx.status}
                    </span>
                  </td>
                  <td className="py-3 text-xs text-zinc-500">{tx.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <h3 className="mb-3 text-sm font-semibold text-white">Quick Actions</h3>
          <div className="flex flex-wrap gap-2">
            <button className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-300 transition hover:border-white/20 hover:text-white cursor-pointer">
              <i className="ri-user-add-line"></i> Add User
            </button>
            <button className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-300 transition hover:border-white/20 hover:text-white cursor-pointer">
              <i className="ri-file-list-3-line"></i> View Reports
            </button>
            <button className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-300 transition hover:border-white/20 hover:text-white cursor-pointer">
              <i className="ri-settings-3-line"></i> Settings
            </button>
          </div>
        </div>
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <h3 className="mb-3 text-sm font-semibold text-white">System Status</h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-400">API</span>
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Operational
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-400">Delivery Bot</span>
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Online
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-400">Payment Gateway</span>
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Online
              </span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}