import { TrendingUp } from "lucide-react";

function LegalShell({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="border-b border-border-subtle bg-bg-surface">
        <div className="max-w-3xl mx-auto px-5 py-4 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center">
              <TrendingUp size={16} className="text-white" />
            </div>
            <span className="font-semibold text-white">TradingAgents</span>
          </a>
          <a href="/" className="text-sm text-accent hover:underline">Back to home</a>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-5 py-10">
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        <p className="text-xs text-text-muted mt-1 mb-8">Last updated: {updated}</p>
        <div className="space-y-6 text-sm text-text-secondary leading-relaxed [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-text-primary [&_h2]:mt-2">
          {children}
        </div>
      </main>
    </div>
  );
}

export function Terms() {
  return (
    <LegalShell title="Terms of Service" updated="July 3, 2026">
      <section>
        <h2>1. What TradingAgents is</h2>
        <p className="mt-2">
          TradingAgents is an educational paper-trading simulation platform. All trades are
          executed with virtual money through Alpaca's paper-trading API. No real money is
          ever deposited, traded, or at risk on this platform.
        </p>
      </section>
      <section>
        <h2>2. Not financial advice</h2>
        <p className="mt-2">
          AI-generated analyses, signals, and simulated trades are provided for educational
          and entertainment purposes only. They are not investment advice, and TradingAgents
          is not a registered investment adviser or broker-dealer. Simulated performance does
          not represent — and does not predict — real trading returns. Do not base real
          investment decisions on this platform's output.
        </p>
      </section>
      <section>
        <h2>3. Your account</h2>
        <p className="mt-2">
          You are responsible for keeping your password confidential and for activity on your
          account. You may connect your own Alpaca paper-trading API keys; those keys are
          encrypted at rest and used only to operate your simulated account. We may suspend
          accounts that abuse the service (automated scraping, attempting to access other
          users' data, or excessive load).
        </p>
      </section>
      <section>
        <h2>4. Service availability</h2>
        <p className="mt-2">
          The service is provided "as is", without warranties of any kind. We may modify,
          suspend, or discontinue features at any time. We are not liable for losses of any
          kind arising from use of the platform — including decisions you make elsewhere
          after seeing content here.
        </p>
      </section>
      <section>
        <h2>5. Changes</h2>
        <p className="mt-2">
          We may update these terms; continued use after an update constitutes acceptance.
          Material changes will be noted on this page's "Last updated" date.
        </p>
      </section>
    </LegalShell>
  );
}

export function Privacy() {
  return (
    <LegalShell title="Privacy Policy" updated="July 3, 2026">
      <section>
        <h2>1. What we collect</h2>
        <p className="mt-2">
          Account data (email, optional name, a hashed password), your Alpaca paper-trading
          API keys (encrypted at rest — we never see or store them in plain text), the
          simulated trading data your account generates, and basic product usage events
          (e.g. sign-ins, analyses run) used to improve the service.
        </p>
      </section>
      <section>
        <h2>2. What we don't collect</h2>
        <p className="mt-2">
          No real brokerage credentials, no payment information, no government IDs, no
          advertising trackers, and no sale of your data to anyone — ever.
        </p>
      </section>
      <section>
        <h2>3. How data is used</h2>
        <p className="mt-2">
          To operate your account, execute simulated trades you request, send account emails
          (verification, password reset), and understand aggregate product usage. Public
          pages (such as the track record) show only anonymized platform-wide aggregates —
          never data attributable to you.
        </p>
      </section>
      <section>
        <h2>4. Third parties</h2>
        <p className="mt-2">
          Your simulated trades are executed via Alpaca (paper API) under your own Alpaca
          account and their privacy policy. AI analysis requests are processed by our LLM
          providers without your personal identity attached. Infrastructure providers host
          our servers and database.
        </p>
      </section>
      <section>
        <h2>5. Your choices</h2>
        <p className="mt-2">
          You can disconnect your broker keys at any time in Settings (they are deleted, not
          retained). To delete your account and its data entirely, contact us and we will
          remove it.
        </p>
      </section>
    </LegalShell>
  );
}
