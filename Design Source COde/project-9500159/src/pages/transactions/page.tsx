const transactions = [
  {
    id: "#TXN-4821",
    item: "OG Renegade Raider Account",
    price: 449,
    status: "Completed",
    date: "May 10, 2026",
    type: "Purchase",
  },
  {
    id: "#TXN-4815",
    item: "Galaxy Skin + 120 Skins",
    price: 189,
    status: "Completed",
    date: "May 8, 2026",
    type: "Purchase",
  },
  {
    id: "#TXN-4792",
    item: "Account Deposit",
    price: 500,
    status: "Completed",
    date: "May 5, 2026",
    type: "Deposit",
  },
  {
    id: "#TXN-4761",
    item: "Black Knight + 250 Skins",
    price: 249,
    status: "Refunded",
    date: "May 1, 2026",
    type: "Purchase",
  },
  {
    id: "#TXN-4720",
    item: "Ghoul Trooper Account",
    price: 159,
    status: "Completed",
    date: "Apr 28, 2026",
    type: "Purchase",
  },
  {
    id: "#TXN-4689",
    item: "Account Deposit",
    price: 200,
    status: "Completed",
    date: "Apr 25, 2026",
    type: "Deposit",
  },
  {
    id: "#TXN-4650",
    item: "Aerial Assault Trooper",
    price: 329,
    status: "Completed",
    date: "Apr 20, 2026",
    type: "Purchase",
  },
  {
    id: "#TXN-4601",
    item: "Warranty Extension",
    price: 25,
    status: "Completed",
    date: "Apr 18, 2026",
    type: "Service",
  },
];

export default function TransactionHistory() {
  const totalSpent = transactions
    .filter((t) => t.type === "Purchase" && t.status !== "Refunded")
    .reduce((sum, t) => sum + t.price, 0);

  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="glass-panel rounded-3xl px-4 py-6 sm:px-6 sm:py-8 md:px-8">
        <h1 className="text-glow font-space text-2xl font-bold text-white sm:text-3xl md:text-4xl">
          Transaction History
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          View all your purchases, deposits, and refunds in one place.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Total Spent</p>
          <p className="mt-1 text-2xl font-bold text-white">${totalSpent.toLocaleString()}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Total Transactions</p>
          <p className="mt-1 text-2xl font-bold text-white">{transactions.length}</p>
        </div>
        <div className="glass-panel rounded-2xl p-4 sm:p-5">
          <p className="text-xs text-zinc-500">Account Balance</p>
          <p className="mt-1 text-2xl font-bold text-emerald-400">$142.00</p>
        </div>
      </section>

      <section className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs text-zinc-500">
                <th className="pb-3 pr-4 font-medium">Transaction ID</th>
                <th className="pb-3 pr-4 font-medium">Item / Description</th>
                <th className="pb-3 pr-4 font-medium">Type</th>
                <th className="pb-3 pr-4 font-medium">Amount</th>
                <th className="pb-3 pr-4 font-medium">Status</th>
                <th className="pb-3 font-medium">Date</th>
              </tr>
            </thead>
            <tbody className="text-zinc-400">
              {transactions.map((tx) => (
                <tr key={tx.id} className="border-b border-white/5 last:border-0">
                  <td className="py-3 pr-4 text-xs font-mono text-zinc-500">{tx.id}</td>
                  <td className="py-3 pr-4 text-white">{tx.item}</td>
                  <td className="py-3 pr-4">
                    <span className="rounded-md bg-white/5 px-2 py-0.5 text-[11px] text-zinc-400">
                      {tx.type}
                    </span>
                  </td>
                  <td className="py-3 pr-4 font-medium text-white">
                    {tx.type === "Deposit" || tx.status === "Refunded" ? (
                      <span className={tx.status === "Refunded" ? "text-emerald-400" : ""}>
                        {tx.status === "Refunded" ? "+" : "+"}${tx.price}
                      </span>
                    ) : (
                      <span className="text-zinc-300">-${tx.price}</span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <span
                      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${
                        tx.status === "Completed"
                          ? "bg-emerald-500/10 text-emerald-400"
                          : tx.status === "Refunded"
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "bg-amber-500/10 text-amber-400"
                      }`}
                    >
                      {tx.status}
                    </span>
                  </td>
                  <td className="py-3 text-xs text-zinc-500">{tx.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}