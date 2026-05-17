import { useState } from "react";
import Header from "./components/Header";
import FilterPanel from "./components/FilterPanel";
import AccountGrid from "./components/AccountGrid";

export default function Home() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [bannerVisible, setBannerVisible] = useState(true);

  return (
    <div className="min-h-screen bg-background bg-grid-pattern">
      {/* Announcement bar */}
      {bannerVisible && (
        <div className="relative bg-primary/10 border-b border-primary/20 px-4 py-2 flex items-center justify-center gap-3">
          <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shrink-0" />
          <p className="text-xs font-bold text-primary tracking-wide text-center">
            🎮 &nbsp;Join our Discord community for exclusive deals &mdash;
            <a href="https://discord.cg/fortniteaccount" target="_blank" rel="nofollow noreferrer" className="underline ml-1 hover:text-primary/70 transition-colors">
              discord.cg/fortniteaccount
            </a>
          </p>
          <button
            className="absolute right-3 text-primary/50 hover:text-primary transition-colors cursor-pointer w-4 h-4 flex items-center justify-center"
            onClick={() => setBannerVisible(false)}
            aria-label="Close"
          >
            <i className="ri-close-line text-sm" />
          </button>
        </div>
      )}

      <Header
        onMenuToggle={() => setMobileMenuOpen((v) => !v)}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
      />

      <div className="flex">
        {/* Mobile sidebar overlay */}
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/70 lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Mobile sidebar */}
        <aside
          className={`fixed top-0 left-0 z-50 h-full w-72 bg-card border-r border-border transform transition-transform duration-300 lg:hidden ${
            mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="h-full flex flex-col pt-14">
            <button
              className="absolute top-3 right-3 p-1.5 rounded-lg bg-secondary hover:bg-card-hover transition-colors cursor-pointer border border-border"
              onClick={() => setMobileMenuOpen(false)}
            >
              <i className="ri-close-line text-foreground text-sm w-4 h-4 flex items-center justify-center" />
            </button>
            <FilterPanel />
          </div>
        </aside>

        {/* Desktop sidebar */}
        <aside className="hidden lg:block w-64 xl:w-72 shrink-0">
          <div className="sticky top-[49px] h-[calc(100vh-49px)] bg-card border-r border-border overflow-hidden">
            <FilterPanel />
          </div>
        </aside>

        {/* Main content */}
        <AccountGrid />
      </div>
    </div>
  );
}