function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer
      role="contentinfo"
      aria-label="Government of India - Portal Footer"
      style={{
        backgroundColor: 'var(--govt-blue-dark)',
        color: '#ffffff',
        padding: '2rem 0',
        marginTop: 'auto',
        borderTop: '3px solid var(--govt-blue-light)'
      }}
    >
      <div style={{
        maxWidth: '1400px',
        margin: '0 auto',
        padding: '0 1.5rem'
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          gap: '2rem',
          marginBottom: '1.5rem'
        }}>
          {/* PRISM Brand in Footer */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.75rem' }}>
              <img
                src="/prism-symbol-transparent.png"
                alt="PRISM Emblem"
                style={{ width: '24px', height: '24px', objectFit: 'contain' }}
              />
              <h5 style={{ margin: 0, fontSize: '1.1rem', fontWeight: '800', color: '#ffffff', letterSpacing: '1px' }}>
                PRISM
              </h5>
            </div>
            <p style={{
              margin: 0,
              fontSize: '0.85rem',
              color: '#94a3b8',
              lineHeight: '1.6'
            }}>
              Evidence Integrity & Intelligence Layer (EIIL) for public infrastructure monitoring, audit, and tamper-evident verification.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '1rem', color: '#ffffff' }}>
              Quick Links
            </h5>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '0.5rem' }}>
                <a href="#" style={{ color: '#adb5bd', textDecoration: 'none', fontSize: '0.85rem' }}>
                  About Us
                </a>
              </li>
              <li style={{ marginBottom: '0.5rem' }}>
                <a href="#" style={{ color: '#adb5bd', textDecoration: 'none', fontSize: '0.85rem' }}>
                  Help Desk
                </a>
              </li>
              <li>
                <a href="#" style={{ color: '#adb5bd', textDecoration: 'none', fontSize: '0.85rem' }}>
                  Contact
                </a>
              </li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '1rem', color: '#ffffff' }}>
              Contact
            </h5>
            <p style={{
              margin: 0,
              fontSize: '0.85rem',
              color: '#adb5bd',
              lineHeight: '1.6'
            }}>
              Ministry of Electronics & IT<br />
              Government of India<br />
              Email: support@proofofaction.gov.in
            </p>
          </div>
        </div>

        {/* Copyright */}
        <div style={{
          paddingTop: '1rem',
          borderTop: '1px solid var(--govt-blue-light)',
          textAlign: 'center'
        }}>
          <p style={{
            margin: 0,
            fontSize: '0.8rem',
            color: '#dee2e6'
          }}>
            © {currentYear} Government of India. All rights reserved.
          </p>
          <p style={{
            margin: '0.25rem 0 0 0',
            fontSize: '0.75rem',
            color: '#ced4da'
          }}>
            This is a computer-based system. Unauthorized access is prohibited.
          </p>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
