import { useEffect, useState } from 'react';

export function GreetingBar({ onOpenBrief }) {
  const [timeStr, setTimeStr] = useState('');
  const [greeting, setGreeting] = useState('Good Evening');
  const username = localStorage.getItem('helios_user') || sessionStorage.getItem('helios_user') || 'Operator';

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const h = now.getHours();
      const g = h < 12 ? 'Good Morning' : h < 17 ? 'Good Afternoon' : 'Good Evening';
      setGreeting(g);

      const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      const pad = (n) => String(n).padStart(2, '0');

      setTimeStr(
        `${pad(now.getHours())}:${pad(now.getMinutes())} · ${days[now.getDay()]}, ${months[now.getMonth()]} ${now.getDate()}`
      );
    };

    updateTime();
    const timer = setInterval(updateTime, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="greeting-bar">
      <div className="greeting-left">
        <div className="greeting-text">{greeting}, {username}</div>
        <div className="greeting-sub">
          <span className="greeting-sec-badge">
            <span className="greeting-sec-dot"></span>Secured
          </span>
          <span className="greeting-time">{timeStr}</span>
        </div>
      </div>
      <button className="daily-brief-btn" onClick={onOpenBrief} title="Generate AI Daily Intelligence Briefing">
        <div className="daily-brief-icon">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 2.8l1.15 4.15a3.2 3.2 0 0 0 2.2 2.2L19.5 10.3l-4.15 1.15a3.2 3.2 0 0 0-2.2 2.2L12 17.8l-1.15-4.15a3.2 3.2 0 0 0-2.2-2.2L4.5 10.3l4.15-1.15a3.2 3.2 0 0 0 2.2-2.2L12 2.8z" />
            <path d="M19 3.2v3.1M17.45 4.75h3.1" />
            <path d="M5.2 16.8v2.3M4.05 17.95h2.3" />
          </svg>
        </div>
        <div className="daily-brief-text">
          <div className="daily-brief-title">Daily Brief</div>
          <div className="daily-brief-desc">AI intelligence · 24h</div>
        </div>
      </button>
    </div>
  );
}
