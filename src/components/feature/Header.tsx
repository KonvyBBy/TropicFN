
export default function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 z-40 bg-black bg-opacity-80 backdrop-blur-md border-b border-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center">
            <h1
              className="text-2xl font-bold bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent"
              style={{ fontFamily: '"Pacifico", serif' }}
            >
              logo
            </h1>
          </div>

          {/* Navigation */}
          <nav className="hidden md:flex items-center space-x-8">
            <a href="#" className="text-gray-300 hover:text-white transition-colors">
              Home
            </a>
            <a href="#" className="text-gray-300 hover:text-white transition-colors">
              Products
            </a>
            <a href="#" className="text-gray-300 hover:text-white transition-colors">
              About
            </a>
            <a href="#" className="text-gray-300 hover:text-white transition-colors">
              Contact
            </a>
          </nav>

          {/* Mobile menu button */}
          <button className="md:hidden text-gray-300 hover:text-white">
            <i className="ri-menu-line text-xl"></i>
          </button>
        </div>
      </div>
    </header>
  );
}
