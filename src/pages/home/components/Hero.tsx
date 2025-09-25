
export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-black">
      {/* Background Image */}
      <div 
        className="absolute inset-0 z-0"
        style={{
          backgroundImage: `url('https://readdy.ai/api/search-image?query=Epic%20gaming%20setup%20with%20futuristic%20black%20and%20white%20aesthetic%2C%20professional%20esports%20environment%2C%20gaming%20monitors%20and%20keyboards%2C%20minimalist%20design%20with%20high%20contrast%20lighting%2C%20modern%20technology%20workspace%2C%20sleek%20gaming%20peripherals&width=1920&height=1080&seq=hero-bg&orientation=landscape')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat'
        }}
      >
        <div className="absolute inset-0 bg-black/60"></div>
      </div>

      {/* Grid Pattern Overlay */}
      <div className="absolute inset-0 z-10">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/20 to-black/80"></div>
        <div 
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: `
              linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)
            `,
            backgroundSize: '50px 50px',
            animation: 'grid-move 20s linear infinite'
          }}
        ></div>
      </div>

      {/* Content */}
      <div className="relative z-20 text-center px-4 max-w-6xl mx-auto">
        <div className="mb-8">
          <div className="inline-flex items-center px-6 py-2 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full mb-6">
            <i className="ri-shield-check-line text-white mr-2"></i>
            <span className="text-white text-sm font-medium">100% Secure & Verified Accounts</span>
          </div>
        </div>

        <h1 className="text-5xl md:text-7xl font-bold text-white mb-6 leading-tight">
          Premium <span className="gradient-text">Fortnite</span>
          <br />
          Accounts Available
        </h1>

        <p className="text-xl md:text-2xl text-gray-300 mb-12 max-w-3xl mx-auto leading-relaxed">
          Get instant access to legendary skins, rare emotes, and exclusive items. 
          All accounts come with lifetime warranty and 24/7 support.
        </p>

        {/* CTA Buttons */}
        <div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16">
          <button className="bg-white hover:bg-gray-200 text-black px-8 py-4 rounded-lg font-bold text-lg transition-all duration-300 transform hover:scale-105 animate-glow whitespace-nowrap">
            <i className="ri-shopping-cart-line mr-2"></i>
            Browse Accounts
          </button>
          <button className="border-2 border-white text-white hover:bg-white hover:text-black px-8 py-4 rounded-lg font-bold text-lg transition-all duration-300 transform hover:scale-105 whitespace-nowrap">
            <i className="ri-play-circle-line mr-2"></i>
            Watch Demo
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl mx-auto">
          <div className="text-center">
            <div className="text-4xl font-bold text-white mb-2">15,000+</div>
            <div className="text-gray-400">Happy Customers</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold text-white mb-2">99.9%</div>
            <div className="text-gray-400">Success Rate</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold text-white mb-2">24/7</div>
            <div className="text-gray-400">Customer Support</div>
          </div>
        </div>
      </div>

      {/* Floating Elements */}
      <div className="absolute top-20 left-10 w-4 h-4 bg-white rounded-full opacity-60 animate-float"></div>
      <div className="absolute top-40 right-20 w-6 h-6 bg-gray-400 rounded-full opacity-40 animate-float" style={{ animationDelay: '1s' }}></div>
      <div className="absolute bottom-40 left-20 w-5 h-5 bg-white rounded-full opacity-50 animate-float" style={{ animationDelay: '2s' }}></div>
      <div className="absolute bottom-20 right-10 w-3 h-3 bg-gray-300 rounded-full opacity-70 animate-float" style={{ animationDelay: '0.5s' }}></div>

      {/* Scroll Indicator */}
      <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 z-20">
        <div className="flex flex-col items-center text-gray-400">
          <span className="text-sm mb-2">Scroll to explore</span>
          <div className="w-6 h-10 border-2 border-gray-400 rounded-full flex justify-center">
            <div className="w-1 h-3 bg-gray-400 rounded-full mt-2 animate-bounce"></div>
          </div>
        </div>
      </div>
    </section>
  );
}
