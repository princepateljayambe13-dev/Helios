import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Helios Dashboard Caught Render Error:', error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#000000',
            color: '#f2f2f0',
            fontFamily: 'Montserrat, sans-serif',
            padding: '24px',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              maxWidth: '480px',
              padding: '32px',
              background: '#101010',
              border: '1px solid #282828',
              borderRadius: '12px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '16px',
            }}
          >
            <div
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '50%',
                background: 'rgba(239, 82, 81, 0.15)',
                display: 'grid',
                placeItems: 'center',
                color: '#EF5251',
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                <path d="M12 9v4M12 17h.01" />
              </svg>
            </div>
            <h2 style={{ fontSize: '16px', margin: 0, letterSpacing: '0.5px' }}>TELEMETRY INTERFACE RECOVERY</h2>
            <p style={{ fontSize: '12.5px', color: '#9a9a96', margin: 0, lineHeight: 1.5 }}>
              The GSOC console encountered a render interruption. Telemetry pipelines remain active in the background.
            </p>
            {this.state.error && (
              <div
                style={{
                  width: '100%',
                  background: '#080808',
                  padding: '10px 14px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontFamily: '"IBM Plex Sans", sans-serif',
                  color: '#EF5251',
                  textAlign: 'left',
                  overflowX: 'auto',
                }}
              >
                {this.state.error.message || String(this.state.error)}
              </div>
            )}
            <button
              onClick={this.handleReload}
              style={{
                marginTop: '8px',
                background: '#EF5251',
                color: '#fff',
                border: 'none',
                padding: '8px 20px',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              Reload Console
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
