import { useState } from "react";

const warrantyFaqs = [
  {
    question: "What does the warranty cover?",
    answer:
      "Our warranty covers account recovery issues, login failures due to credential changes by previous owners, and any account bans that occur within the warranty period that were not caused by the buyer's actions.",
  },
  {
    question: "How long is the warranty period?",
    answer:
      "Full Access (FA) accounts come with a 30-day warranty. Non-Full Access (NFA) accounts come with a 7-day warranty. Extended warranties can be purchased at checkout for an additional fee.",
  },
  {
    question: "What is not covered by warranty?",
    answer:
      "Warranty does not cover bans due to cheating, account sharing, VPN usage on flagged IPs, or any violation of Epic Games' Terms of Service by the buyer. It also does not cover forgotten credentials after successful delivery.",
  },
  {
    question: "How do I file a warranty claim?",
    answer:
      "Open a support ticket within your warranty period. Include your order ID, a description of the issue, and screenshots if applicable. Our team will review and respond within 24 hours.",
  },
  {
    question: "What happens if my account is banned?",
    answer:
      "If the account is banned due to no fault of your own within the warranty period, we will provide a replacement account of equal or greater value. If no suitable replacement is available, a refund will be issued.",
  },
];

export default function Warranty() {
  const [activeFaq, setActiveFaq] = useState<number | null>(0);

  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="glass-panel rounded-3xl px-4 py-6 sm:px-6 sm:py-8 md:px-8">
        <h1 className="text-glow font-space text-2xl font-bold text-white sm:text-3xl md:text-4xl">
          Warranty Policy
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-400 md:text-base">
          We stand behind every account sold on Konvy. Here is everything you need to know about our coverage.
        </p>
      </header>

      <section className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6">
        <h2 className="mb-4 font-space text-lg font-semibold text-white sm:text-xl">
          Warranty FAQ
        </h2>
        <div className="space-y-2">
          {warrantyFaqs.map((faq, index) => (
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

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="glass-panel rounded-2xl p-5 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/10">
            <i className="ri-shield-check-line text-2xl text-emerald-400"></i>
          </div>
          <h3 className="text-sm font-semibold text-white">30 Day FA Warranty</h3>
          <p className="mt-1 text-xs text-zinc-500">Full Access accounts backed for 30 days</p>
        </div>
        <div className="glass-panel rounded-2xl p-5 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/10">
            <i className="ri-refresh-line text-2xl text-emerald-400"></i>
          </div>
          <h3 className="text-sm font-semibold text-white">Free Replacements</h3>
          <p className="mt-1 text-xs text-zinc-500">Equal or better value account swap</p>
        </div>
        <div className="glass-panel rounded-2xl p-5 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/10">
            <i className="ri-customer-service-2-line text-2xl text-emerald-400"></i>
          </div>
          <h3 className="text-sm font-semibold text-white">24h Response</h3>
          <p className="mt-1 text-xs text-zinc-500">Claims reviewed within one business day</p>
        </div>
      </section>
    </div>
  );
}