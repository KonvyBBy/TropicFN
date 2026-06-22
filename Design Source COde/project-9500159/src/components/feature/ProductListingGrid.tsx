import { useState } from "react";
import ProductCard from "./ProductCard";

const mockProducts = [
  {
    id: 1,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "OG Renegade Raider Account",
    description: "Full access account with Renegade Raider, Aerial Assault Trooper, and 200+ skins. 950+ wins, level 350.",
    price: 449,
    originalPrice: 599,
    rating: 5,
    reviews: 128,
    tags: ["OG", "Full Access", "PC"],
    sold: 89,
  },
  {
    id: 2,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "Aerial Assault Trooper + 150 Skins",
    description: "Rare OG skin account with Galaxy, Ikonik, Travis Scott, and exclusive battle pass skins from Chapter 1-4.",
    price: 329,
    originalPrice: 429,
    rating: 5,
    reviews: 94,
    tags: ["Rare", "150+ Skins", "Full Access"],
    sold: 67,
  },
  {
    id: 3,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "GFA Account - Galaxy + 120 Skins",
    description: "Stacked Galaxy skin account with Travis Scott, Marshmello, Ninja, and 120+ skins. Email changeable.",
    price: 189,
    rating: 4,
    reviews: 73,
    tags: ["GFA", "120+ Skins", "Email Change"],
    sold: 156,
  },
  {
    id: 4,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "NFA Stacked - 250+ Skins Black Knight",
    description: "Incredibly stacked account with Black Knight, Omega, Dark Knight, and every battle pass skin.",
    price: 249,
    originalPrice: 349,
    rating: 5,
    reviews: 211,
    tags: ["NFA", "250+ Skins", "Black Knight"],
    sold: 134,
  },
  {
    id: 5,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "Ghoul Trooper + Reaper Account",
    description: "Full access with Ghoul Trooper, Reaper pickaxe, and 80+ skins. Great starter stacked account.",
    price: 159,
    rating: 4,
    reviews: 45,
    tags: ["Full Access", "80+ Skins", "Starter"],
    sold: 92,
  },
  {
    id: 6,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "Recon Expert + Blue Squire Bundle",
    description: "Rare combo account with Recon Expert, Blue Squire, Royale Knight, and 100+ skins.",
    price: 199,
    rating: 5,
    reviews: 67,
    tags: ["Full Access", "100+ Skins", "Rare Combo"],
    sold: 78,
  },
  {
    id: 7,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "Honor Guard + Wonder Skin Account",
    description: "Exclusive promo skins with Honor Guard and Wonder skin. 90+ total skins, full email access.",
    price: 89,
    rating: 4,
    reviews: 38,
    tags: ["Full Access", "90+ Skins", "Promo"],
    sold: 145,
  },
  {
    id: 8,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "NFA - Max Omega + Ragnarok + Dire",
    description: "Chapter 1 maxed battle pass skins with Omega, Ragnarok, Dire, and Calamity. 180+ skins.",
    price: 119,
    originalPrice: 179,
    rating: 4,
    reviews: 82,
    tags: ["NFA", "180+ Skins", "Max BP"],
    sold: 203,
  },
  {
    id: 9,
    image: "https://storage.readdy-site.link/project_files/2c597b3c-b681-4ae1-be2e-32fd4db69a21/5bf4bd1f-2f5c-4d60-8eb2-8ee21dd76121_b80645519041812a6a9d729ace2f592e-1.png?v=4aba63448fbff6a833eca4217d9b6a1f",
    title: "Merry Marauder + Crackshot Account",
    description: "Holiday exclusive skins with Merry Marauder, Crackshot, and Ginger Gunner. 70+ skins, GFA.",
    price: 129,
    rating: 5,
    reviews: 56,
    tags: ["GFA", "70+ Skins", "Holiday"],
    sold: 88,
  },
];

export default function ProductListingGrid() {
  const [isLoading, setIsLoading] = useState(false);

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {isLoading ? (
        <div className="glass-panel col-span-full rounded-2xl p-5 text-center md:p-6">
          <p className="text-base font-semibold text-white">Loading listings, please wait</p>
          <div className="mt-3 inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300 [animation-delay:-0.3s]"></span>
            <span className="h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300/85 [animation-delay:-0.15s]"></span>
            <span className="h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300/70"></span>
          </div>
        </div>
      ) : (
        mockProducts.map((product) => (
          <ProductCard
            key={product.id}
            image={product.image}
            title={product.title}
            description={product.description}
            price={product.price}
            originalPrice={product.originalPrice}
            rating={product.rating}
            reviews={product.reviews}
            tags={product.tags}
            sold={product.sold}
          />
        ))
      )}
    </section>
  );
}