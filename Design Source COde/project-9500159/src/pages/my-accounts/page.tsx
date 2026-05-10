const myAccounts = [
  {
    id: "ACC-1024",
    title: "OG Renegade Raider Account",
    skins: 247,
    vBucks: 2450,
    level: 352,
    wins: 984,
    status: "Active",
    purchased: "May 10, 2026",
    warranty: "28 days left",
    email: "j*****@gmail.com",
    password: "********",
  },
  {
    id: "ACC-1018",
    title: "Galaxy Skin + 120 Skins",
    skins: 128,
    vBucks: 890,
    level: 210,
    wins: 456,
    status: "Active",
    purchased: "May 8, 2026",
    warranty: "26 days left",
    email: "f*****@yahoo.com",
    password: "********",
  },
  {
    id: "ACC-995",
    title: "Ghoul Trooper Starter",
    skins: 86,
    vBucks: 120,
    level: 175,
    wins: 312,
    status: "Active",
    purchased: "Apr 28, 2026",
    warranty: "15 days left",
    email: "g*****@outlook.com",
    password: "********",
  },
  {
    id: "ACC-960",
    title: "Aerial Assault Trooper",
    skins: 154,
    vBucks: 3400,
    level: 298,
    wins: 712,
    status: "Expired",
    purchased: "Apr 20, 2026",
    warranty: "Expired",
    email: "a*****@proton.me",
    password: "********",
  },
];

export default function MyAccounts() {
  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="glass-panel rounded-3xl px-4 py-6 sm:px-6 sm:py-8 md:px-8">
        <h1 className="text-glow font-space text-2xl font-bold text-white sm:text-3xl md:text-4xl">
          My Accounts
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          Manage your purchased accounts, view credentials, and check warranty status.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Total Accounts</p>
          <p className="mt-1 text-2xl font-bold text-white">{myAccounts.length}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Active Warranties</p>
          <p className="mt-1 text-2xl font-bold text-emerald-400">
            {myAccounts.filter((a) => a.status === "Active").length}
          </p>
        </div>
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Total Skins Owned</p>
          <p className="mt-1 text-2xl font-bold text-white">
            {myAccounts.reduce((sum, a) => sum + a.skins, 0).toLocaleString()}
          </p>
        </div>
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Total vBucks</p>
          <p className="mt-1 text-2xl font-bold text-white">
            {myAccounts.reduce((sum, a) => sum + a.vBucks, 0).toLocaleString()}
          </p>
        </div>
      </section>

      <section className="space-y-4">
        {myAccounts.map((account) => (
          <div key={account.id} className="glass-panel rounded-2xl p-4 sm:p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex-1 space-y-3">
                <div className="flex items-center gap-3">
                  <h3 className="text-sm font-semibold text-white">{account.title}</h3>
                  <span
                    className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                      account.status === "Active"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : "bg-red-500/10 text-red-400"
                    }`}
                  >
                    {account.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div className="rounded-lg border border-white/5 bg-black/25 px-3 py-2">
                    <p className="text-[10px] text-zinc-500">Skins</p>
                    <p className="text-sm font-medium text-white">{account.skins}</p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-black/25 px-3 py-2">
                    <p className="text-[10px] text-zinc-500">vBucks</p>
                    <p className="text-sm font-medium text-white">{account.vBucks.toLocaleString()}</p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-black/25 px-3 py-2">
                    <p className="text-[10px] text-zinc-500">Level</p>
                    <p className="text-sm font-medium text-white">{account.level}</p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-black/25 px-3 py-2">
                    <p className="text-[10px] text-zinc-500">Wins</p>
                    <p className="text-sm font-medium text-white">{account.wins}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-4 text-xs text-zinc-500">
                  <span>Purchased: {account.purchased}</span>
                  <span>Warranty: {account.warranty}</span>
                </div>
              </div>

              <div className="flex flex-col gap-2 sm:w-56">
                <div className="space-y-1.5">
                  <label className="text-[10px] text-zinc-500">Email</label>
                  <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <span className="text-xs text-zinc-400">{account.email}</span>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] text-zinc-500">Password</label>
                  <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                    <span className="text-xs text-zinc-400">{account.password}</span>
                  </div>
                </div>
                <button className="mt-1 inline-flex h-9 items-center justify-center rounded-lg px-3 text-xs font-medium transition bg-white/5 text-zinc-300 hover:bg-white/10 border border-white/10 cursor-pointer whitespace-nowrap">
                  <i className="ri-file-copy-line mr-1.5"></i>
                  Copy Credentials
                </button>
              </div>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}