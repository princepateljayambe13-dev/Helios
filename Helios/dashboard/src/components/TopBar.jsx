import { useState } from 'react';
import logoImg from '../assets/89AAFAAC-3B6A-4DE1-B2E3-0BFA195F4A6F_1_201_a-Photoroom copy.png';

export function TopBar({ connected, onOpenSearch, onLogout, onSelectTab, onToggleMenu, mobileMenuOpen }) {
  const [imgFailed, setImgFailed] = useState(false);
  const username = localStorage.getItem('helios_user') || sessionStorage.getItem('helios_user') || 'Admin';

  return (
    <div className="topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        {/* Mobile / Tablet Menu Hamburger Toggle */}
        <button
          className="mobile-menu-btn"
          onClick={onToggleMenu}
          aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
          title={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
        >
          {mobileMenuOpen ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          )}
        </button>

        <div
          className="brand"
          style={{ cursor: onSelectTab ? 'pointer' : 'default' }}
          onClick={() => onSelectTab && onSelectTab('overview')}
          title="Helios Overview Dashboard"
        >
          {!imgFailed ? (
            <img
              src={logoImg}
              alt="HELIOS"
              className="brand-logo"
              onError={() => setImgFailed(true)}
            />
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div className="brand-mark">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="5" />
                  <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                </svg>
              </div>
              <span className="brand-name">HELIOS</span>
            </div>
          )}
        </div>
      </div>

      <div className="topbar-right">
        {/* Mobile Search Icon Button */}
        <button
          className="search-mobile-btn"
          onClick={onOpenSearch}
          title="Search event, track, plate (⌘ K)"
          aria-label="Search"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </button>

        {/* Desktop / Tablet Search Input Box */}
        <div className="search" onClick={onOpenSearch} title="Click or press ⌘ K to search & ask AI">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="search-text">Search event, track, plate…</span>
          <span className="kbd-hint">⌘ K</span>
        </div>


        <div className={`conn-pill ${connected ? '' : 'disconnected'}`}>
          <span className="conn-dot"></span>
          <span className="conn-text">{connected ? 'LIVE' : 'OFFLINE'}</span>
        </div>

        <div
          className="avatar"
          onClick={onLogout}
          title={`Signed in as ${username}. Click to log out.`}
          style={{ cursor: 'pointer', userSelect: 'none' }}
          aria-label={`User profile (${username}) - Click to log out`}
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="currentColor"
            style={{ display: 'block' }}
          >
            <circle cx="12" cy="7.5" r="4.8" />
            <path d="M3.5 20.5c0-3.8 3.8-7 8.5-7s8.5 3.2 8.5 7H3.5z" />
          </svg>
        </div>
      </div>
    </div>
  );
}
