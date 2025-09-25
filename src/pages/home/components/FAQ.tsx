
import { useState } from 'react';

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const faqs = [
    {
      question: "How quickly will I receive my Fortnite account?",
      answer: "All accounts are delivered instantly after payment confirmation. You'll receive login details via email within 2-5 minutes, along with setup instructions and warranty information."
    },
    {
      question: "Are the accounts safe and legitimate?",
      answer: "Yes, all our accounts are 100% legitimate and manually verified. Each account is obtained through official channels and comes with full ownership transfer and lifetime warranty protection."
    },
    {
      question: "What if the account gets banned or compromised?",
      answer: "We offer lifetime warranty on all accounts. If your account faces any issues, we'll provide a free replacement within 24 hours. Our accounts have a 99.9% success rate with zero ban history."
    },
    {
      question: "Can I change the email and password?",
      answer: "Absolutely! You get full access to change email, password, and all account settings. We provide step-by-step guides to help you secure your new account properly."
    },
    {
      question: "What payment methods do you accept?",
      answer: "We accept all major credit cards, PayPal, cryptocurrency, and various digital payment methods. All transactions are SSL encrypted and processed securely."
    },
    {
      question: "Do you offer refunds?",
      answer: "We offer a 7-day money-back guarantee if you're not satisfied. However, due to our rigorous testing process, refund requests are extremely rare."
    }
  ];

  return (
    <section id="faq" className="py-20 bg-black">
      <div className="container mx-auto px-4">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-white mb-6">
            Frequently Asked <span className="gradient-text">Questions</span>
          </h2>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Everything you need to know about our premium Fortnite accounts
          </p>
        </div>

        <div className="max-w-4xl mx-auto">
          {faqs.map((faq, index) => (
            <div 
              key={index}
              className="mb-4 bg-gray-900/50 backdrop-blur-sm border border-gray-800 rounded-xl overflow-hidden hover:border-gray-700 transition-all duration-300"
            >
              <button
                onClick={() => setOpenIndex(openIndex === index ? null : index)}
                className="w-full px-8 py-6 text-left flex items-center justify-between group hover:bg-gray-800/30 transition-colors"
              >
                <h3 className="text-lg font-semibold text-white group-hover:text-gray-200 transition-colors pr-4">
                  {faq.question}
                </h3>
                <div className={`w-8 h-8 rounded-full bg-white flex items-center justify-center flex-shrink-0 transition-transform duration-300 ${openIndex === index ? 'rotate-180' : ''}`}>
                  <i className="ri-arrow-down-s-line text-black"></i>
                </div>
              </button>
              
              <div className={`overflow-hidden transition-all duration-300 ${openIndex === index ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}`}>
                <div className="px-8 pb-6">
                  <p className="text-gray-400 leading-relaxed">
                    {faq.answer}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Contact CTA */}
        <div className="text-center mt-16">
          <div className="inline-flex items-center px-6 py-3 bg-gray-800/50 border border-gray-600 rounded-full backdrop-blur-sm mb-6">
            <i className="ri-question-line text-white mr-3"></i>
            <span className="text-gray-300">Still have questions?</span>
          </div>
          <div>
            <button className="bg-white hover:bg-gray-200 text-black px-8 py-3 rounded-lg font-semibold transition-all duration-300 transform hover:scale-105 mr-4 whitespace-nowrap">
              <i className="ri-customer-service-2-line mr-2"></i>
              Contact Support
            </button>
            <button className="border border-gray-600 text-gray-300 hover:bg-white hover:text-black hover:border-white px-8 py-3 rounded-lg font-semibold transition-all duration-300 whitespace-nowrap">
              <i className="ri-discord-line mr-2"></i>
              Join Discord
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
