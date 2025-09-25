
import Hero from './components/Hero'
import ProductGrid from './components/ProductGrid'
import TrustSection from './components/TrustSection'
import FAQ from './components/FAQ'
import Header from '../../components/feature/Header'
import Footer from '../../components/feature/Footer'

export default function HomePage() {
  return (
    <div className="min-h-screen bg-black text-white">
      <Header />
      <Hero />
      <ProductGrid />
      <TrustSection />
      <FAQ />
      <Footer />
    </div>
  )
}
