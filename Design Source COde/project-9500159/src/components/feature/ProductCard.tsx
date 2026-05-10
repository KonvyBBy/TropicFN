interface ProductCardProps {
  image: string;
  title: string;
  description: string;
  price: number;
  originalPrice?: number;
  rating: number;
  reviews: number;
  tags: string[];
  sold: number;
}

export default function ProductCard({
  image,
  title,
  description,
  price,
  originalPrice,
  rating,
  reviews,
  tags,
  sold,
}: ProductCardProps) {
  return (
    <div className="glass-panel group relative overflow-hidden rounded-2xl transition hover:border-white/20">
      <div className="relative aspect-[16/10] overflow-hidden">
        <img
          src={image}
          alt={title}
          className="h-full w-full object-cover object-top transition duration-500 group-hover:scale-105"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent"></div>
        {originalPrice && (
          <span className="absolute left-3 top-3 rounded-lg bg-red-500/90 px-2 py-1 text-[11px] font-semibold text-white">
            SALE
          </span>
        )}
      </div>
      <div className="p-4 sm:p-5">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-medium text-zinc-300"
            >
              {tag}
            </span>
          ))}
        </div>
        <h3 className="mb-1 text-sm font-semibold text-white line-clamp-1">{title}</h3>
        <p className="mb-3 text-xs text-zinc-400 line-clamp-2">{description}</p>
        <div className="flex items-center gap-1 mb-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <i
              key={i}
              className={`ri-star-fill text-xs ${
                i < Math.floor(rating) ? "text-amber-400" : "text-zinc-600"
              }`}
            ></i>
          ))}
          <span className="ml-1 text-[11px] text-zinc-500">
            ({reviews}) {sold} sold
          </span>
        </div>
        <div className="flex items-end justify-between">
          <div>
            {originalPrice && (
              <span className="mr-2 text-xs text-zinc-500 line-through">
                ${originalPrice}
              </span>
            )}
            <span className="text-lg font-bold text-white">${price}</span>
          </div>
          <button className="inline-flex items-center justify-center rounded-xl px-3 py-2 text-xs font-medium transition bg-white text-black hover:bg-zinc-200 active:scale-[0.99] whitespace-nowrap cursor-pointer">
            View Details
          </button>
        </div>
      </div>
    </div>
  );
}