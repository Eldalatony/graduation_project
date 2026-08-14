import styles from './page.module.css';

const Bolt = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M13 2L4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5z" />
  </svg>
);
const Check = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 6L9 17l-5-5" />
  </svg>
);
const Dash = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
    <path d="M5 12h14" />
  </svg>
);
const I = ({ d, size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    {d}
  </svg>
);

const icons = {
  plug: <I d={<><path d="M9 2v6M15 2v6" /><path d="M6 8h12v3a6 6 0 0 1-12 0V8z" /><path d="M12 17v5" /></>} />,
  wifi: <I d={<><path d="M5 12.5a10 10 0 0 1 14 0" /><path d="M8.5 16a5 5 0 0 1 7 0" /><circle cx="12" cy="19.5" r="1" fill="currentColor" /></>} />,
  monitor: <I d={<><rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" /><path d="M6 11l3-3 3 2 4-4" /></>} />,
  pulse: <I d={<path d="M3 12h4l2 6 4-14 2 8h6" />} />,
  brain: <I d={<><path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 5 1" /><path d="M15 3a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-5 1" /><path d="M12 3v18" /></>} />,
  alert: <I d={<><path d="M10.3 3.3a2 2 0 0 1 3.4 0l8 14A2 2 0 0 1 20 20H4a2 2 0 0 1-1.7-2.7z" /><path d="M12 9v4M12 17h.01" /></>} />,
  clock: <I d={<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>} />,
  remote: <I d={<><rect x="8" y="2" width="8" height="20" rx="3" /><path d="M12 6v3" /><circle cx="12" cy="15" r="1.6" fill="currentColor" /></>} />,
  lock: <I d={<><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /><path d="M12 15v2" /></>} />,
  home: <I d={<><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M9 20v-6h6v6" /></>} />,
  building: <I d={<><rect x="4" y="3" width="16" height="18" rx="1.5" /><path d="M9 7h.01M15 7h.01M9 11h.01M15 11h.01M9 15h.01M15 15h.01" /><path d="M10 21v-3h4v3" /></>} />,
  office: <I d={<><path d="M3 21h18" /><path d="M6 21V7l7-4v18" /><path d="M13 21V9l5 3v9" /><path d="M9 8h.01M9 12h.01M9 16h.01" /></>} />,
};

const features = [
  { icon: icons.pulse, title: 'Live Monitoring', text: 'Voltage, current, and power readings updated every second straight from the device.' },
  { icon: icons.brain, title: 'AI Forecasting', text: 'Predicts your monthly bill before it arrives so there are no surprises at month-end.' },
  { icon: icons.alert, title: 'Anomaly Detection', text: 'Alerts you when a device behaves abnormally or is left running too long.' },
  { icon: icons.clock, title: 'Smart Scheduling', text: 'Automate on/off times with cron-based or simple timer schedules.' },
  { icon: icons.remote, title: 'Remote Control', text: 'Toggle any appliance from anywhere, right from the dashboard.' },
  { icon: icons.lock, title: 'End-to-End Encryption', text: 'AES-256 payload encryption plus a TLS tunnel on every single message.' },
];

const steps = [
  { icon: icons.plug, title: 'Plug In', text: 'Connect the SHEMMS device to any outlet and power your appliance through it.' },
  { icon: icons.wifi, title: 'Connect', text: 'Link the device to your home Wi-Fi from the dashboard in under 2 minutes.' },
  { icon: icons.monitor, title: 'Monitor', text: 'Access live energy data, AI insights, and controls from anywhere.' },
];

const audience = [
  { icon: icons.home, title: 'Homeowners', text: 'Reduce your electricity bill and get notified before appliances fail.' },
  { icon: icons.building, title: 'Property Managers', text: 'Monitor energy across multiple units from a single dashboard.' },
  { icon: icons.office, title: 'Small Offices', text: 'Track equipment usage, automate off-hours shutdowns, and cut waste.' },
];

const metrics = [
  { value: '±0.3%', label: 'Measurement Accuracy' },
  { value: '< 1.2s', label: 'Relay Response Time' },
  { value: '92%', label: 'Forecasting Accuracy' },
  { value: 'AES-256', label: 'Encryption Standard' },
];

const plans = [
  {
    name: 'Free', price: '$0', unit: '/month', cta: 'Start Free', popular: false,
    rows: [
      { label: '1 device' }, { label: '7-day history' },
      { label: 'AI Analytics', state: 'no' }, { label: 'Basic anomaly alerts' },
      { label: 'Scheduling', state: 'no' }, { label: 'API access', state: 'no' },
      { label: 'Community support' },
    ],
  },
  {
    name: 'Pro', price: '$9.99', unit: '/month', cta: 'Start Pro Trial', popular: true,
    rows: [
      { label: 'Up to 5 devices' }, { label: '1-year history' },
      { label: 'AI Analytics', state: 'yes' }, { label: 'Advanced anomaly alerts' },
      { label: 'Scheduling', state: 'yes' }, { label: 'API access', state: 'no' },
      { label: 'Email support' },
    ],
  },
  {
    name: 'Enterprise', price: 'Custom', unit: '', cta: 'Contact Sales', popular: false,
    rows: [
      { label: 'Unlimited devices' }, { label: 'Unlimited history' },
      { label: 'AI Analytics', state: 'yes' }, { label: 'Advanced anomaly alerts' },
      { label: 'Scheduling', state: 'yes' }, { label: 'API access', state: 'yes' },
      { label: 'Dedicated support' },
    ],
  },
];

const barHeights = [42, 65, 50, 80, 58, 92, 70, 84, 62, 96];

export default function LandingPage() {
  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <a href="#top" className={styles.brand}>
            <span className={styles.boltBadge}><Bolt size={16} /></span>
          </a>
          <nav className={styles.navLinks}>
            <a href="#features" className={styles.navLink}>Features</a>
            <a href="#how" className={styles.navLink}>How It Works</a>
            <a href="#pricing" className={styles.navLink}>Pricing</a>
            <a href="#contact" className={styles.navLink}>Contact</a>
          </nav>
          <div className={styles.navRight}>
            <a href="#" className={styles.loginLink}>Login</a>
            <a href="#" className={`${styles.btn} ${styles.btnPrimary}`}>Get Started</a>
          </div>
        </div>
      </header>

      <main id="top">
        <section className={styles.hero}>
          <div className={styles.container}>
            <div className={styles.heroGrid}>
              <div>
                <span className={styles.eyebrow}><Bolt size={13} /> Smart Home Energy</span>
                <h1 className={styles.heroTitle}>
                  Take Control of Your<br />Home&apos;s <span className={styles.accent}>Energy</span>
                </h1>
                <p className={styles.heroSub}>
                  Real-time monitoring, AI-powered forecasting, and smart automation — all in one device.
                </p>
                <div className={styles.heroCtas}>
                  <a href="#" className={`${styles.btn} ${styles.btnPrimary}`}>Get Started</a>
                  <a href="#how" className={`${styles.btn} ${styles.btnOutline}`}>See How It Works</a>
                </div>
                <div className={styles.trustRow}>
                  <span className={styles.trustBadge}><Check size={15} /> AES-256 Encrypted</span>
                  <span className={styles.trustBadge}><Check size={15} /> No Hub Required</span>
                  <span className={styles.trustBadge}><Check size={15} /> Works with any outlet</span>
                </div>
              </div>

              <div className={styles.mockup}>
                <div className={styles.mockBar}>
                  <span className={`${styles.dot} ${styles.dotR}`} />
                  <span className={`${styles.dot} ${styles.dotY}`} />
                  <span className={`${styles.dot} ${styles.dotG}`} />
                  <span className={styles.mockTabLabel}>app.shemms.io/dashboard</span>
                </div>
                <div className={styles.mockBody}>
                  <div className={styles.mockTopRow}>
                    <span className={styles.mockTitle}>Living Room — Air Conditioner</span>
                    <span className={styles.mockLive}><span className={styles.liveDot} /> LIVE</span>
                  </div>
                  <div className={styles.mockStats}>
                    <div className={styles.mockStat}>
                      <div className={styles.mockStatLabel}>Voltage</div>
                      <div className={styles.mockStatValue}>220<span>V</span></div>
                    </div>
                    <div className={styles.mockStat}>
                      <div className={styles.mockStatLabel}>Current</div>
                      <div className={styles.mockStatValue}>4.8<span>A</span></div>
                    </div>
                    <div className={styles.mockStat}>
                      <div className={styles.mockStatLabel}>Power</div>
                      <div className={styles.mockStatValue}>1.05<span>kW</span></div>
                    </div>
                  </div>
                  <div className={styles.mockChart}>
                    {barHeights.map((h, i) => (
                      <span key={i} className={styles.bar} style={{ height: `${h}%` }} />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="how" className={`${styles.section} ${styles.sectionAlt}`}>
          <div className={styles.container}>
            <div className={styles.sectionHead}>
              <div className={styles.kicker}>How It Works</div>
              <h2 className={styles.sectionTitle}>Up and running in three steps</h2>
              <p className={styles.sectionDesc}>No electrician, no hub, no complicated setup.</p>
            </div>
            <div className={styles.steps}>
              {steps.map((s, i) => (
                <div key={s.title} className={styles.stepCard}>
                  <span className={styles.stepNum}>{i + 1}</span>
                  <div className={styles.iconWrap}>{s.icon}</div>
                  <h3 className={styles.cardTitle}>{s.title}</h3>
                  <p className={styles.cardText}>{s.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="features" className={styles.section}>
          <div className={styles.container}>
            <div className={styles.sectionHead}>
              <div className={styles.kicker}>Features</div>
              <h2 className={styles.sectionTitle}>Everything in a single smart device</h2>
              <p className={styles.sectionDesc}>
                Monitoring, intelligence, automation, and security — without juggling apps.
              </p>
            </div>
            <div className={styles.featureGrid}>
              {features.map((f) => (
                <div key={f.title} className={styles.featureCard}>
                  <div className={styles.iconWrap}>{f.icon}</div>
                  <h3 className={styles.cardTitle}>{f.title}</h3>
                  <p className={styles.cardText}>{f.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="pricing" className={`${styles.section} ${styles.sectionAlt}`}>
          <div className={styles.container}>
            <div className={styles.sectionHead}>
              <div className={styles.kicker}>Pricing</div>
              <h2 className={styles.sectionTitle}>Plans that scale with you</h2>
              <p className={styles.sectionDesc}>Start free. Upgrade when you need more devices and AI.</p>
            </div>
            <div className={styles.pricingGrid}>
              {plans.map((plan) => (
                <div key={plan.name} className={`${styles.planCard} ${plan.popular ? styles.planPopular : ''}`}>
                  {plan.popular && <span className={styles.popularBadge}>Most Popular</span>}
                  <div className={styles.planName}>{plan.name}</div>
                  <div className={styles.planPrice}>
                    <span className={styles.planPriceNum}>{plan.price}</span>
                    {plan.unit && <span className={styles.planPriceUnit}>{plan.unit}</span>}
                  </div>
                  <div className={styles.planDivider} />
                  <ul className={styles.planFeatures}>
                    {plan.rows.map((row) => (
                      <li key={row.label}>
                        {row.state === 'no'
                          ? <span className={styles.checkNo}><Dash /></span>
                          : <span className={styles.checkYes}><Check /></span>}
                        <span className={row.state === 'no' ? styles.featMuted : ''}>{row.label}</span>
                      </li>
                    ))}
                  </ul>
                  <a
                    href="#"
                    className={`${styles.btn} ${plan.popular ? styles.btnPrimary : styles.btnOutline}`}
                    style={{ width: '100%' }}
                  >
                    {plan.cta}
                  </a>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.container}>
            <div className={styles.competitor}>
              <p>
                Unlike basic smart plugs, <span className={styles.accent}>SHEMMS</span> is the only device
                with built-in AI forecasting, anomaly detection, and privacy-preserving encryption.
              </p>
            </div>
          </div>
        </section>

        <section className={`${styles.section} ${styles.sectionAlt}`}>
          <div className={styles.container}>
            <div className={styles.sectionHead}>
              <div className={styles.kicker}>Who It&apos;s For</div>
              <h2 className={styles.sectionTitle}>Built for every kind of space</h2>
            </div>
            <div className={styles.audienceGrid}>
              {audience.map((a) => (
                <div key={a.title} className={styles.stepCard}>
                  <div className={styles.iconWrap}>{a.icon}</div>
                  <h3 className={styles.cardTitle}>{a.title}</h3>
                  <p className={styles.cardText}>{a.text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.metricsBar}>
          <div className={styles.container}>
            <div className={styles.metricsGrid}>
              {metrics.map((m) => (
                <div key={m.label}>
                  <div className={styles.metricValue}>{m.value}</div>
                  <div className={styles.metricLabel}>{m.label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.ctaBanner}>
          <div className={styles.container}>
            <h2 className={styles.ctaTitle}>Ready to take control of your energy?</h2>
            <p className={styles.ctaSub}>Start free. No credit card required.</p>
            <a href="#" className={`${styles.btn} ${styles.btnPrimary} ${styles.btnLarge}`}>Get Started</a>
          </div>
        </section>
      </main>

      <footer id="contact" className={styles.footer}>
        <div className={styles.container}>
          <div className={styles.footerGrid}>
            <div>
              <span className={styles.brand}>
                <span className={styles.boltBadge}><Bolt size={16} /></span>
                SHEMMS
              </span>
              <p className={styles.footerTagline}>
                Smart home energy monitoring, forecasting, and automation in a single secure device.
              </p>
            </div>
            <div className={styles.footerCol}>
              <h4 className={styles.footerColTitle}>Product</h4>
              <a href="#features">Features</a>
              <a href="#pricing">Pricing</a>
              <a href="#">Docs</a>
            </div>
            <div className={styles.footerCol}>
              <h4 className={styles.footerColTitle}>Company</h4>
              <a href="#">About</a>
              <a href="#contact">Contact</a>
            </div>
            <div className={styles.footerCol}>
              <h4 className={styles.footerColTitle}>Legal</h4>
              <a href="#">Privacy</a>
              <a href="#">Terms</a>
            </div>
          </div>
          <div className={styles.footerBottom}>© 2025 SHEMMS. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}
