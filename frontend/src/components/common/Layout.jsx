import Header from './Header';
import Footer from './Footer';
import Sidebar from './Sidebar';
import { Outlet } from 'react-router-dom';

function Layout() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      minHeight: '100vh',
      backgroundColor: 'var(--govt-gray-off-white)'
    }}>
      {/* WCAG AA Accessible Skip to Main Content Link */}
      <a href="#main-content" className="skip-to-content">
        Skip to main content
      </a>

      <Header />
      <div style={{
        display: 'flex',
        flex: 1,
        minHeight: 'calc(100vh - 64px)',
      }}>
        <Sidebar />
        <main
          id="main-content"
          role="main"
          tabIndex="-1"
          style={{
            flex: 1,
            minWidth: 0,
            backgroundColor: 'var(--govt-gray-off-white)',
            overflowY: 'auto',
            outline: 'none',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ flex: 1 }}>
            <Outlet />
          </div>
          <Footer />
        </main>
      </div>
    </div>
  );
}

export default Layout;
