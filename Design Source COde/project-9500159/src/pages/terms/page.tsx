export default function Terms() {
  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="glass-panel rounded-3xl px-4 py-6 sm:px-6 sm:py-8 md:px-8">
        <h1 className="text-glow font-space text-2xl font-bold text-white sm:text-3xl md:text-4xl">
          Terms of Service
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          Last updated: May 2026
        </p>
      </header>

      <div className="glass-panel rounded-3xl p-4 sm:p-5 md:p-6 space-y-6">
        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">1. Account Ownership</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            Konvy Accounts acts as a marketplace connecting buyers and sellers of digital game accounts. We do not own the accounts listed on our platform. All accounts are sold by third-party sellers who have verified ownership.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">2. Prohibited Activities</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            Buyers may not use purchased accounts for cheating, exploiting, or any activity that violates the game publisher's Terms of Service. Doing so voids all warranties and may result in account termination. Reselling accounts purchased from Konvy without our authorization is strictly prohibited.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">3. Payment & Delivery</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            All payments are processed securely. Account credentials are delivered automatically to your registered email and dashboard upon payment confirmation. Delivery typically occurs within seconds. If you do not receive credentials within 5 minutes, contact support immediately.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">4. Refund Policy</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            Due to the digital nature of our products, all sales are final. Refunds are only issued in cases where the account cannot be delivered or the account is non-functional at the time of delivery. Warranty replacements take priority over refunds.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">5. User Conduct</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            Users must provide accurate information during registration. Fraudulent chargebacks, fake dispute claims, or abuse of our support system will result in permanent account suspension and potential legal action.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">6. Limitation of Liability</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            Konvy Accounts is not liable for any indirect, incidental, or consequential damages arising from the use of purchased accounts. Our maximum liability is limited to the purchase price of the account in question.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">7. Changes to Terms</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            We reserve the right to modify these terms at any time. Continued use of the platform after changes constitutes acceptance of the updated terms. Users will be notified of material changes via email.
          </p>
        </section>

        <section>
          <h2 className="mb-2 font-space text-base font-semibold text-white sm:text-lg">8. Contact</h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            For any questions about these Terms of Service, please contact us at support@konvyaccounts.com or open a ticket through our Support page.
          </p>
        </section>
      </div>
    </div>
  );
}