import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";
import Footer from "./Footer";

export default function Layout() {
  return (
    <div className="bg-grain relative min-h-screen overflow-x-hidden bg-background font-manrope text-foreground">
      {/* Ambient glow orbs */}
      <div className="absolute inset-0 -z-10 opacity-70 pointer-events-none">
        <div className="absolute -left-40 top-16 h-72 w-72 rounded-full bg-white/10 blur-[120px]"></div>
        <div className="absolute right-0 top-32 h-80 w-80 rounded-full bg-zinc-300/10 blur-[130px]"></div>
        <div className="absolute bottom-0 left-1/3 h-96 w-96 rounded-full bg-zinc-500/10 blur-[150px]"></div>
      </div>

      <div className="mx-auto w-full max-w-[1300px] px-3 pb-[calc(4rem+env(safe-area-inset-bottom))] pt-4 sm:px-4 sm:pt-5 md:px-8 md:pt-6">
        <Navbar />
        <main className="space-y-5 pt-1 sm:space-y-6 sm:pt-2 md:space-y-7 md:pt-3">
          <Outlet />
        </main>
      </div>
      <Footer />
    </div>
  );
}