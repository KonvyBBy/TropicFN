
export default function TrustSection() {
  const features = [
    {
      icon: 'ri-shield-check-line',
      title: 'Lifetime Warranty',
      description: 'Every account comes with lifetime protection. If anything goes wrong, we provide free replacement within 24 hours.',
      color: 'text-white'
    },
    {
      icon: 'ri-time-line',
      title: 'Instant Delivery',
      description: 'Get your account details immediately after purchase. No waiting, no delays - start playing within minutes.',
      color: 'text-white'
    },
    {
      icon: 'ri-customer-service-2-line',
      title: '24/7 Support',
      description: 'Our dedicated support team is available around the clock to help with any questions or issues.',
      color: 'text-white'
    },
    {
      icon: 'ri-lock-line',
      title: 'Secure Transactions',
      description: 'All payments are processed through secure, encrypted channels with full buyer protection.',
      color: 'text-white'
    },
    {
      icon: 'ri-star-line',
      title: 'Premium Quality',
      description: 'Each account is carefully selected and verified to ensure you get the rarest and most valuable items.',
      color: 'text-white'
    },
    {
      icon: 'ri-refresh-line',
      title: 'Full Access',
      description: 'Change passwords, email, and settings. You get complete ownership with full account control.',
      color: 'text-white'
    }
  ];

  const stats = [
    { number: '15,000+', label: 'Happy Customers', icon: 'ri-user-line' },
    { number: '99.9%', label: 'Success Rate', icon: 'ri-trophy-line' },
    { number: '5 Min', label: 'Avg Delivery', icon: 'ri-timer-line' },
    { number: '24/7', label: 'Support', icon: 'ri-headphone-line' }
  ];

  return (
    <section className="py-20 bg-black">
      <div className="container mx-auto px-4">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-white mb-6">
            Why Choose <span className="gradient-text">Konvy Accounts</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-3xl mx-auto">
            We've built our reputation on trust, quality, and exceptional service. 
            Here's what makes us the #1 choice for premium Fortnite accounts.
          </p>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-20">
          {stats.map((stat, index) => (
            <div key={index} className="text-center">
              <div className="w-16 h-16 bg-gray-900 border border-gray-700 rounded-xl flex items-center justify-center mx-auto mb-4 hover:bg-white hover:border-white transition-all duration-300 group">
                <i className={`${stat.icon} text-2xl text-white group-hover:text-black transition-colors`}></i>
              </div>
              <div className="text-3xl font-bold text-white mb-2">{stat.number}</div>
              <div className="text-gray-400">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 mb-16">
          {features.map((feature, index) => (
            <div 
              key={index}
              className="bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl p-8 hover:border-gray-600 hover:bg-gray-800/50 transition-all duration-300 group"
            >
              <div className="w-14 h-14 bg-gray-800 border border-gray-700 rounded-xl flex items-center justify-center mb-6 group-hover:bg-white group-hover:border-white transition-all duration-300">
                <i className={`${feature.icon} text-2xl ${feature.color} group-hover:text-black transition-colors`}></i>
              </div>
              
              <h3 className="text-xl font-bold text-white mb-4 group-hover:text-white transition-colors">
                {feature.title}
              </h3>
              
              <p className="text-gray-400 leading-relaxed group-hover:text-gray-300 transition-colors">
                {feature.description}
              </p>
            </div>
          ))}
        </div>

        {/* Trust Badges */}
        <div className="bg-gray-900/30 backdrop-blur-sm border border-gray-800 rounded-2xl p-8">
          <div className="text-center mb-8">
            <h3 className="text-2xl font-bold text-white mb-4">Trusted by Thousands</h3>
            <p className="text-gray-400">Join our community of satisfied customers</p>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="flex items-center justify-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <div className="text-center">
                <i className="ri-shield-star-line text-3xl text-white mb-2"></i>
                <div className="text-sm text-gray-300">SSL Secured</div>
              </div>
            </div>
            
            <div className="flex items-center justify-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <div className="text-center">
                <i className="ri-money-dollar-circle-line text-3xl text-white mb-2"></i>
                <div className="text-sm text-gray-300">Money Back</div>
              </div>
            </div>
            
            <div className="flex items-center justify-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <div className="text-center">
                <i className="ri-customer-service-line text-3xl text-white mb-2"></i>
                <div className="text-sm text-gray-300">Live Support</div>
              </div>
            </div>
            
            <div className="flex items-center justify-center p-4 bg-gray-800/50 rounded-lg border border-gray-700">
              <div className="text-center">
                <i className="ri-verified-badge-line text-3xl text-white mb-2"></i>
                <div className="text-sm text-gray-300">Verified</div>
              </div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center mt-16">
          <button className="bg-white hover:bg-gray-200 text-black px-8 py-4 rounded-lg font-bold text-lg transition-all duration-300 transform hover:scale-105 mr-4 whitespace-nowrap">
            <i className="ri-shopping-cart-line mr-2"></i>
            Shop Now
          </button>
          <button className="border-2 border-white text-white hover:bg-white hover:text-black px-8 py-4 rounded-lg font-bold text-lg transition-all duration-300 transform hover:scale-105 whitespace-nowrap">
            <i className="ri-question-line mr-2"></i>
            Learn More
          </button>
        </div>
      </div>
    </section>
  );
}
