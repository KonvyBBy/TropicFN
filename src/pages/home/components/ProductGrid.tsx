
import { useState, useEffect } from 'react';
import Card from '../../../components/base/Card';

interface Product {
  id: string;
  title: string;
  handle: string;
  description: string;
  featuredImage?: {
    url: string;
    altText?: string;
  };
  priceRange: {
    minVariantPrice: {
      amount: string;
      currencyCode: string;
    };
  };
  variants: {
    edges: Array<{
      node: {
        id: string;
        title: string;
        quantityAvailable: number;
        price: {
          amount: string;
          currencyCode: string;
        };
      };
    }>;
  };
  tags: string[];
}

export default function ProductGrid() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingProduct, setLoadingProduct] = useState<string | null>(null);

  useEffect(() => {
    fetchProducts();
  }, []);

  const fetchProducts = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_PUBLIC_SUPABASE_URL}/functions/v1/get-product-details`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${import.meta.env.VITE_PUBLIC_SUPABASE_ANON_KEY}`,
        },
        body: JSON.stringify({ limit: 12 })
      });

      if (response.ok) {
        const data = await response.json();
        setProducts(data.products || []);
      }
    } catch (error) {
      console.error('Error fetching products:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleBuyNow = async (productId: string, variantId: string) => {
    setLoadingProduct(productId);
    
    try {
      const response = await fetch(`${import.meta.env.VITE_PUBLIC_SUPABASE_URL}/functions/v1/shopify-checkout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${import.meta.env.VITE_PUBLIC_SUPABASE_ANON_KEY}`,
        },
        body: JSON.stringify({
          variantId: variantId,
          quantity: 1
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.checkoutUrl) {
          window.open(data.checkoutUrl, '_blank');
        }
      } else {
        alert('Failed to create checkout. Please try again.');
      }
    } catch (error) {
      console.error('Error creating checkout:', error);
      alert('Something went wrong. Please try again.');
    } finally {
      setLoadingProduct(null);
    }
  };

  const formatPrice = (amount: string, currencyCode: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currencyCode,
    }).format(parseFloat(amount));
  };

  const getRarityColor = (tags: string[]) => {
    if (tags.some(tag => tag.toLowerCase().includes('legendary'))) return 'text-yellow-400';
    if (tags.some(tag => tag.toLowerCase().includes('epic'))) return 'text-gray-300';
    if (tags.some(tag => tag.toLowerCase().includes('rare'))) return 'text-gray-400';
    return 'text-gray-500';
  };

  const getRarityBadge = (tags: string[]) => {
    if (tags.some(tag => tag.toLowerCase().includes('legendary'))) return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
    if (tags.some(tag => tag.toLowerCase().includes('epic'))) return 'bg-gray-500/20 text-gray-300 border-gray-500/30';
    if (tags.some(tag => tag.toLowerCase().includes('rare'))) return 'bg-gray-600/20 text-gray-400 border-gray-600/30';
    return null; // Don't show standard badge
  };

  const hasSpecialRarity = (tags: string[]) => {
    return tags.some(tag => ['legendary', 'epic', 'rare'].some(rarity => tag.toLowerCase().includes(rarity)));
  };

  if (loading) {
    return (
      <section className="py-20 bg-black">
        <div className="container mx-auto px-4">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-6">
              Featured <span className="gradient-text">Accounts</span>
            </h2>
            <p className="text-xl text-gray-400">
              Hand-picked premium accounts with rare items
            </p>
          </div>
          
          <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
            {[...Array(8)].map((_, index) => (
              <div key={index} className="bg-gray-900 rounded-xl p-6 animate-pulse">
                <div className="h-48 bg-gray-800 rounded-lg mb-4"></div>
                <div className="h-6 bg-gray-800 rounded mb-2"></div>
                <div className="h-4 bg-gray-800 rounded mb-4"></div>
                <div className="h-10 bg-gray-800 rounded"></div>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section id="products" className="py-20 bg-black" data-product-shop>
      <div className="container mx-auto px-4">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-white mb-6">
            Featured <span className="gradient-text">Accounts</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Hand-picked premium accounts with legendary skins, rare emotes, and exclusive items
          </p>
        </div>

        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
            {products.map((product) => {
              const variant = product.variants.edges[0]?.node;
              const isLoading = loadingProduct === product.id;
              
              return (
                <Card key={product.id} hover className="h-full flex flex-col">
                  <div className="relative">
                    <img
                      src={product.featuredImage?.url || `https://readdy.ai/api/search-image?query=Premium%20Fortnite%20gaming%20account%20showcase%20with%20legendary%20skins%20and%20rare%20items%2C%20dark%20gaming%20aesthetic%20with%20high%20contrast%20lighting%2C%20professional%20esports%20style%20presentation%2C%20sleek%20modern%20design%20with%20black%20background&width=400&height=300&seq=${product.id}&orientation=landscape`}
                      alt={product.featuredImage?.altText || product.title}
                      className="w-full h-48 object-cover rounded-t-xl"
                    />
                    
                    {/* Rarity Badge - only show for special rarities */}
                    {hasSpecialRarity(product.tags) && (
                      <div className={`absolute top-3 left-3 px-2 py-1 rounded-full text-xs font-semibold border backdrop-blur-sm ${getRarityBadge(product.tags)}`}>
                        {product.tags.find(tag => ['legendary', 'epic', 'rare'].some(rarity => tag.toLowerCase().includes(rarity)))}
                      </div>
                    )}

                    {/* In Stock Badge - always show as in stock */}
                    <div className="absolute top-3 right-3 px-2 py-1 bg-green-500/80 text-white text-xs font-semibold rounded-full backdrop-blur-sm">
                      In Stock
                    </div>
                  </div>

                  <div className="p-6 flex flex-col flex-1">
                    <h3 className="text-xl font-bold text-white mb-2 line-clamp-2">
                      {product.title}
                    </h3>
                    
                    <p className="text-gray-400 text-sm mb-4 line-clamp-3 flex-1">
                      {product.description || "Premium Fortnite account with exclusive items and skins"}
                    </p>

                    {/* Tags */}
                    <div className="flex flex-wrap gap-2 mb-4">
                      {product.tags.slice(0, 3).map((tag, index) => (
                        <span
                          key={index}
                          className="px-2 py-1 bg-gray-800 text-gray-300 text-xs rounded-full"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>

                    <div className="mt-auto">
                      <div className="flex items-center justify-between mb-4">
                        <div className="text-2xl font-bold text-white">
                          {variant ? formatPrice(variant.price.amount, variant.price.currencyCode) : 'N/A'}
                        </div>
                        <div className="flex items-center text-sm text-gray-400">
                          <i className="ri-shield-check-line mr-1"></i>
                          Warranty
                        </div>
                      </div>

                      <button
                        onClick={() => variant && handleBuyNow(product.id, variant.id)}
                        disabled={isLoading || !variant}
                        className="w-full bg-white hover:bg-gray-200 disabled:bg-gray-600 disabled:cursor-not-allowed text-black disabled:text-gray-400 px-6 py-3 rounded-lg font-semibold transition-all duration-300 transform hover:scale-105 disabled:hover:scale-100 whitespace-nowrap"
                      >
                        {isLoading ? (
                          <div className="flex items-center justify-center">
                            <div className="animate-spin rounded-full h-4 w-4 border-2 border-black border-t-transparent mr-2"></div>
                            Processing...
                          </div>
                        ) : (
                          <>
                            <i className="ri-shopping-cart-line mr-2"></i>
                            Buy Now
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>

          {/* View All Button */}
          <div className="text-center mt-16">
            <button className="border-2 border-white text-white hover:bg-white hover:text-black px-8 py-3 rounded-lg font-semibold transition-all duration-300 transform hover:scale-105 whitespace-nowrap">
              <i className="ri-grid-line mr-2"></i>
              View All Accounts
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
