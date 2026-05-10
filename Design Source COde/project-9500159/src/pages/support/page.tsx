import { useState } from "react";

const faqs = [
  {
    question: "How does instant delivery work?",
    answer:
      "Once your payment is confirmed, you will receive the account credentials instantly via email and your dashboard. Our automated system handles everything - no waiting required.",
  },
  {
    question: "Are the accounts safe to buy?",
    answer:
      "Yes! All accounts are verified and checked before listing. Full Access (FA) accounts come with email change capability, and we provide a replacement guarantee for any issues within 24 hours.",
  },
  {
    question: "What is the difference between FA and NFA?",
    answer:
      "FA (Full Access) means you get full control of the account including email/password changes. NFA (Non-Full Access) means the account works but email changes may not be available. FA accounts cost more but are safer long-term.",
  },
  {
    question: "Do you offer refunds?",
    answer:
      "We offer replacements for any defective accounts within 24 hours of purchase. Refunds are handled on a case-by-case basis for accounts that cannot be replaced.",
  },
  {
    question: "Can I sell my account on Konvy?",
    answer:
      "Yes! We welcome sellers. Contact our support team to become a verified seller and start listing your accounts on our marketplace.",
  },
];

export default function Support() {
  const [activeFaq, setActiveFaq] = useState<number | null>(0);
  const [ticketName, setTicketName] = useState("");
  const [ticketEmail, setTicketEmail] = useState("");
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketMessage, setTicketMessage] = useState("");

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Hero */}
      <header className="glass-panel rounded-3xl px-4 py-6 sm:px-6 sm:py-8 md:px-8">
        <h1 className="text-glow font-space text-2xl font-bold text-white sm:text-3xl md:text-4xl">
          Support Center
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-400 md:text-base">
          Need help? Browse our FAQs or open a support ticket. Our team is here to assist you 24/7.
        </p>
      </header>

      {/* FAQ Section */}
      <section className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6">
        <h2 className="mb-4 font-space text-lg font-semibold text-white sm:text-xl">
          Frequently Asked Questions
        </h2>
        <div className="space-y-2">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className="rounded-xl border border-white/10 bg-black/25 transition"
            >
              <button
                onClick={() => setActiveFaq(activeFaq === index ? null : index)}
                className="flex w-full items-center justify-between px-4 py-3.5 text-left cursor-pointer"
                type="button"
              >
                <span className="text-sm font-medium text-white pr-4">{faq.question}</span>
                <i
                  className={`ri-arrow-down-s-line text-zinc-400 transition-transform ${
                    activeFaq === index ? "rotate-180" : ""
                  }`}
                ></i>
              </button>
              {activeFaq === index && (
                <div className="border-t border-white/10 px-4 py-3">
                  <p className="text-sm leading-relaxed text-zinc-400">{faq.answer}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Contact / Ticket Form */}
      <section className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6">
        <h2 className="mb-4 font-space text-lg font-semibold text-white sm:text-xl">
          Open a Support Ticket
        </h2>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Name</label>
            <input
              type="text"
              value={ticketName}
              onChange={(e) => setTicketName(e.target.value)}
              placeholder="Your name"
              className="h-12 w-full rounded-xl border border-white/15 bg-black/35 px-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Email</label>
            <input
              type="email"
              value={ticketEmail}
              onChange={(e) => setTicketEmail(e.target.value)}
              placeholder="you@example.com"
              className="h-12 w-full rounded-xl border border-white/15 bg-black/35 px-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-xs font-medium text-zinc-400">Subject</label>
            <input
              type="text"
              value={ticketSubject}
              onChange={(e) => setTicketSubject(e.target.value)}
              placeholder="What is your issue about?"
              className="h-12 w-full rounded-xl border border-white/15 bg-black/35 px-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-xs font-medium text-zinc-400">Message</label>
            <textarea
              value={ticketMessage}
              onChange={(e) => setTicketMessage(e.target.value)}
              placeholder="Describe your issue in detail..."
              rows={4}
              maxLength={500}
              className="w-full rounded-xl border border-white/15 bg-black/35 px-4 py-3 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus resize-none"
            />
            <p className="text-[11px] text-zinc-500 text-right">
              {ticketMessage.length}/500
            </p>
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              className="inline-flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium transition focus-visible:shadow-focus disabled:opacity-50 bg-white text-black hover:bg-zinc-200 active:scale-[0.99] whitespace-nowrap cursor-pointer"
            >
              <i className="ri-send-plane-line mr-2"></i>
              Submit Ticket
            </button>
          </div>
        </form>
      </section>

      {/* Contact Info Cards */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="glass-panel rounded-2xl p-4 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/5">
            <i className="ri-mail-line text-lg text-emerald-400"></i>
          </div>
          <h3 className="text-sm font-semibold text-white">Email Support</h3>
          <p className="mt-1 text-xs text-zinc-400">support@konvyaccounts.com</p>
        </div>
        <div className="glass-panel rounded-2xl p-4 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/5">
            <i className="ri-discord-line text-lg text-emerald-400"></i>
          </div>
          <h3 className="text-sm font-semibold text-white">Discord Server</h3>
          <p className="mt-1 text-xs text-zinc-400">discord.gg/konvy</p>
        </div>
        <div className="glass-panel rounded-2xl p-4 text-center sm:col-span-2 lg:col-span-1">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/5">
            <i className="ri-time-line text-lg text-emerald-400"></i>
          </div>
          <h3 className="text-sm font-semibold text-white">Response Time</h3>
          <p className="mt-1 text-xs text-zinc-400">Usually under 2 hours</p>
        </div>
      </section>
    </div>
  );
}