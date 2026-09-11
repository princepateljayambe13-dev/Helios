import { useState } from 'react';
import logoImg from '../assets/89AAFAAC-3B6A-4DE1-B2E3-0BFA195F4A6F_1_201_a-Photoroom copy.png';
import { SurveillanceGlobe } from './SurveillanceGlobe';
import '../login.css';

export function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [keepSignedIn, setKeepSignedIn] = useState(true);
  const [error, setError] = useState('');
  const [logoFailed, setLogoFailed] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    const u = username.trim().toLowerCase();
    const p = password.trim();

    // Check credentials: admin / admin (also accepting user-admin / pass-admin)
    const validUser = u === 'admin' || u === 'user-admin';
    const validPass = p === 'admin' || p === 'pass-admin';

    if (validUser && validPass) {
      if (keepSignedIn) {
        localStorage.setItem('helios_auth', 'true');
        localStorage.setItem('helios_user', username.trim() || 'admin');
      } else {
        sessionStorage.setItem('helios_auth', 'true');
        sessionStorage.setItem('helios_user', username.trim() || 'admin');
      }
      onLogin({ username: username.trim() || 'admin' });
    } else {
      setError('Invalid username or password. Please use admin / admin');
    }
  };

  return (
    <div className="login-shell">
      {/* ===== RIGHT: LOGIN FORM PANEL ===== */}
      <div className="login-formside">
        <div className="login-fs-top">
          {!logoFailed ? (
            <img
              src={logoImg}
              alt="HELIOS"
              className="login-fs-logo"
              onError={() => setLogoFailed(true)}
            />
          ) : (
            <div className="login-brand-fallback">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#C99A5B" strokeWidth="2.2">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
              <span>HELIOS</span>
            </div>
          )}
        </div>

        <div className="login-form-inner">
          <div className="login-fs-eyebrow">
            <span className="dot"></span>
            <span>SECURE ACCESS</span>
          </div>

          <h2>Log in to your account</h2>
          <p className="sub">Enter your credentials to reach your command center.</p>

          {error && (
            <div className="login-error">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} autoComplete="on">
            <div className="login-field">
              <label htmlFor="login-username">Username or Email</label>
              <div className="login-input-wrap">
                <svg className="lead-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <input
                  id="login-username"
                  type="text"
                  placeholder="admin"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="login-password">Password</label>
              <div className="login-input-wrap">
                <svg className="lead-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="5" y="11" width="14" height="10" rx="2" />
                  <path d="M8 11V7a4 4 0 018 0v4" />
                </svg>
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="toggle-icon"
                  onClick={() => setShowPassword((prev) => !prev)}
                  title={showPassword ? 'Hide password' : 'Show password'}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <div className="login-row-between">
              <label className="login-chk">
                <input
                  type="checkbox"
                  checked={keepSignedIn}
                  onChange={(e) => setKeepSignedIn(e.target.checked)}
                />
                Keep me signed in
              </label>
              <span className="login-hint-badge">
                admin / admin
              </span>
            </div>

            <button type="submit" className="login-btn-primary">
              Log in
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          </form>
        </div>

        <div className="login-fs-bottom">
          <span>© 2026 Helios Security</span>
          <span style={{ color: '#7A6A57' }}>
            System v1.0
          </span>
        </div>
      </div>

      {/* ===== LEFT: RADIANT SURVEILLANCE GLOBE HERO PANEL ===== */}
      <div className="login-watch" aria-hidden="true">
        {/* Animated 3D Dotted Surveillance Globe (Cloudflare Connect style) */}
        <SurveillanceGlobe />

        <div className="login-watch-top">
          <div className="login-watch-badge">
            <span className="dot"></span>
            <span>HELIOS DEFENSE & SURVEILLANCE</span>
          </div>
        </div>

        <div className="login-watch-copy">
          <div className="login-tagline">Autonomous Perimeter Intelligence</div>
          <h1>Where security teams connect.</h1>
          <p>
            Autonomous optical tracking, thermal IR imaging, and UAV detection correlated in real time — so your team sees the moment it matters, not the hour after.
          </p>
        </div>
      </div>
    </div>
  );
}
