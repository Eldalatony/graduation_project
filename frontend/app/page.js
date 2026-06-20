'use client';

import { useRouter } from 'next/navigation';
import styles from './welcome.module.css';

export default function WelcomePage() {
  const router = useRouter();

  const handleGetStarted = () => {
    const token = localStorage.getItem('token');
    router.push(token ? '/home' : '/auth');
  };

  return (
    <div className={styles.page}>
      <p className={styles.brand}>SHEMMS</p>

      <h1 className={styles.headline}>
        An IoT-Based Smart Plug for Intelligent Energy Consumption
        Monitoring and Management in <span>Smart Homes</span>
      </h1>

      <p className={styles.sub}>
        Track every appliance in real time, detect anomalies, automate schedules,
        and understand your energy costs — all in one place.
      </p>

      <div className={styles.features}>
        <div className={styles.feature}>Live Readings</div>
        <div className={styles.feature}>Smart Alerts</div>
        <div className={styles.feature}>Automation</div>
        <div className={styles.feature}>Analytics</div>
        <div className={styles.feature}>Encrypted Data</div>
      </div>

      <button className={styles.cta} onClick={handleGetStarted}>
        Get Started
        <span className={styles.ctaArrow}>→</span>
      </button>

      <p className={styles.note}>No credit card required · Free to use</p>
    </div>
  );
}
