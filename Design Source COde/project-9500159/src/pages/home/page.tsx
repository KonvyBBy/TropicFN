import HeroSection from "@/components/feature/HeroSection";
import AnnouncementBanner from "@/components/feature/AnnouncementBanner";
import FilterSection from "@/components/feature/FilterSection";
import ProductListingGrid from "@/components/feature/ProductListingGrid";

export default function Home() {
  return (
    <div className="space-y-5 sm:space-y-6 md:space-y-7">
      <HeroSection />
      <AnnouncementBanner />
      <FilterSection />
      <ProductListingGrid />
    </div>
  );
}