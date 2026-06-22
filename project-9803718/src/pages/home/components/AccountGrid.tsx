import { useState } from "react";
import AccountCard from "./AccountCard";
import { accounts, sortOptions, totalAccounts, totalPages } from "@/mocks/accounts";

const ITEMS_PER_PAGE = 24;

export default function AccountGrid() {
  const [activeSort, setActiveSort] = useState("Default");
  const [currentPage, setCurrentPage] = useState(1);

  const sorted = [...accounts].slice(0, ITEMS_PER_PAGE);

  const getPageNumbers = () => {
    const pages: number[] = [];
    const maxVisible = 7;
    let start = Math.max(1, currentPage - 3);
    const end = Math.min(totalPages, start + maxVisible - 1);
    start = Math.max(1, end - maxVisible + 1);
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  };

  return (
    <main className="flex-1 p-4 md:p-5 min-w-0">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap mb-5">
        {/* Sort tabs */}
        <div className="flex items-center gap-1.5 bg-card border border-border rounded-xl p-1">
          {sortOptions.map((opt) => (
            <button
              key={opt}
              onClick={() => setActiveSort(opt)}
              className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
                activeSort === opt
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>

        {/* Count + pagination */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-card border border-border rounded-xl">
            <div className="w-1.5 h-1.5 rounded-full bg-primary" />
            <span className="text-xs font-bold text-foreground">
              {totalAccounts.toLocaleString()}
            </span>
            <span className="text-xs text-muted-foreground font-medium">accounts</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-card border border-border hover:bg-secondary disabled:opacity-30 transition-colors cursor-pointer"
            >
              <i className="ri-arrow-left-s-line text-foreground text-sm w-4 h-4 flex items-center justify-center" />
            </button>
            <span className="text-xs font-bold text-foreground px-2 min-w-[3.5rem] text-center">
              {currentPage} / {totalPages}
            </span>
            <button
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-card border border-border hover:bg-secondary disabled:opacity-30 transition-colors cursor-pointer"
            >
              <i className="ri-arrow-right-s-line text-foreground text-sm w-4 h-4 flex items-center justify-center" />
            </button>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3">
        {sorted.map((account) => (
          <AccountCard key={account.id} account={account} />
        ))}
      </div>

      {/* Pagination */}
      <div className="flex justify-center gap-1.5 mt-8 flex-wrap">
        <button
          disabled={currentPage === 1}
          onClick={() => setCurrentPage(1)}
          className="h-9 px-3 rounded-xl text-xs font-bold bg-card border border-border text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-30 transition-colors cursor-pointer"
        >
          &lt;&lt;
        </button>
        {getPageNumbers().map((page) => (
          <button
            key={page}
            onClick={() => setCurrentPage(page)}
            className={`w-9 h-9 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              page === currentPage
                ? "bg-primary text-primary-foreground"
                : "bg-card border border-border text-muted-foreground hover:text-foreground hover:bg-secondary"
            }`}
          >
            {page}
          </button>
        ))}
        <button
          disabled={currentPage === totalPages}
          onClick={() => setCurrentPage(totalPages)}
          className="h-9 px-3 rounded-xl text-xs font-bold bg-card border border-border text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-30 transition-colors cursor-pointer"
        >
          &gt;&gt;
        </button>
      </div>
    </main>
  );
}