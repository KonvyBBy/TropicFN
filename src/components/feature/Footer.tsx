
import { Link } from 'react-router-dom';

export default function Footer() {
  const currentYear = new Date().getFullYear();

  const footerSections = [
    {
      title: 'Company',
      links: [
        { name: 'About Us', href: '/about' },
        { name: 'Contact', href: '/contact' },
        { name: 'Careers', href: '/careers' },
        { name: 'Blog', href: '/blog' }
      ]
    },
    {
      title: 'Support',
      links: [
        { name: 'Help Center', href: '/help' },
        { name: 'Live Chat', href: '/chat' },
        { name: 'Discord', href: '/discord' },
        { name: 'Status', href: '/status' }
      ]
    },
    {
      title: 'Legal',
      links: [
        { name: 'Privacy Policy', href: '/privacy' },
        { name: 'Terms of Service', href: '/terms' },
        { name: 'Refund Policy', href: '/refund' },
        { name: 'DMCA', href: '/dmca' }
      ]
    }
  ];

  const socialLinks = [
    { icon: 'ri-twitter-x-line', href: '#', name: 'Twitter' },
    { icon: 'ri-discord-line', href: '#', name: 'Discord' },
    { icon: 'ri-instagram-line', href: '#', name: 'Instagram' },
    { icon: 'ri-youtube-line', href: '#', name: 'YouTube' }
  ];

  return (
    <footer className="bg-black border-t border-gray-800">
      <div className="container mx-auto px-4 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8 mb-12">
          {/* Brand Section */}
          <div className="lg:col-span-2">
            <Link to="/" className="flex items-center mb-6">
              <img 
                src="https://cdn.discordapp.com/attachments/1260081053419311187/1420549514304946308/YAxQWwAAAAZJREFUAwBdtstlWwCl4QAAAABJRU5ErkJggg.png?ex=68d5cd54&is=68d47bd4&hm=b47fb31f436099bb6c96152b5e69ef52ed44806e62524c148d358431ff93e95e&"
                alt="Konvy Accounts"
                className="h-10 w-auto mr-3"
              />
              <span className="text-2xl font-bold text-white" style={{ fontFamily: '"Pacifico", serif' }}>
                Konvy Accounts
              </span>
            </Link>
            <p className="text-gray-400 mb-6 leading-relaxed max-w-md">
              The ultimate destination for premium Fortnite accounts. Get legendary skins, 
              rare emotes, and exclusive items with lifetime warranty protection.
            </p>
            
            {/* Trust Badges */}
            <div className="flex items-center space-x-4 mb-6">
              <div className="flex items-center px-3 py-1 bg-gray-800 border border-gray-600 rounded-full">
                <i className="ri-shield-check-line text-white mr-2 text-sm"></i>
                <span className="text-gray-300 text-xs">SSL Secured</span>
              </div>
              <div className="flex items-center px-3 py-1 bg-gray-800 border border-gray-600 rounded-full">
                <i className="ri-customer-service-2-line text-white mr-2 text-sm"></i>
                <span className="text-gray-300 text-xs">24/7 Support</span>
              </div>
            </div>

            {/* Social Links */}
            <div className="flex space-x-4">
              {socialLinks.map((social) => (
                <a
                  key={social.name}
                  href={social.href}
                  className="w-10 h-10 bg-gray-800 border border-gray-700 rounded-lg flex items-center justify-center hover:bg-white hover:border-white hover:text-black transition-all duration-300 group"
                  aria-label={social.name}
                >
                  <i className={`${social.icon} text-gray-400 group-hover:text-black transition-colors`}></i>
                </a>
              ))}
            </div>
          </div>

          {/* Footer Links */}
          {footerSections.map((section) => (
            <div key={section.title}>
              <h3 className="text-white font-bold mb-4">{section.title}</h3>
              <ul className="space-y-3">
                {section.links.map((link) => (
                  <li key={link.name}>
                    <Link
                      to={link.href}
                      className="text-gray-400 hover:text-white transition-colors"
                    >
                      {link.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Newsletter */}
        <div className="border-t border-gray-800 pt-8 mb-8">
          <div className="max-w-md">
            <h3 className="text-white font-bold mb-3">Stay Updated</h3>
            <p className="text-gray-400 text-sm mb-4">
              Get notified about new premium accounts and exclusive deals
            </p>
            <div className="flex gap-3">
              <input
                type="email"
                placeholder="Enter your email"
                className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-white transition-colors"
              />
              <button className="bg-white hover:bg-gray-200 text-black px-6 py-2 rounded-lg font-semibold transition-all duration-300 whitespace-nowrap">
                Subscribe
              </button>
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="border-t border-gray-800 pt-8 flex flex-col md:flex-row items-center justify-between">
          <div className="text-gray-400 text-sm mb-4 md:mb-0">
            © {currentYear} Konvy Accounts. All rights reserved.
          </div>
          
          <div className="flex items-center space-x-6">
            <div className="text-gray-400 text-sm">
              Powered by{' '}
              <a 
                href="https://readdy.ai/?origin=logo" 
                className="text-white hover:text-gray-300 transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                Readdy
              </a>
            </div>
            
            {/* Payment Methods */}
            <div className="flex items-center space-x-2">
              <div className="w-8 h-5 bg-gray-700 rounded flex items-center justify-center">
                <i className="ri-visa-line text-white text-xs"></i>
              </div>
              <div className="w-8 h-5 bg-gray-700 rounded flex items-center justify-center">
                <i className="ri-mastercard-line text-white text-xs"></i>
              </div>
              <div className="w-8 h-5 bg-gray-700 rounded flex items-center justify-center">
                <i className="ri-paypal-line text-white text-xs"></i>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
