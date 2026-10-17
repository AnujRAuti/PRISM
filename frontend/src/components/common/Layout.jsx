import { useState } from 'react';
import Header from './Header';
import Footer from './Footer';
import Sidebar from './Sidebar';
import { Outlet } from 'react-router-dom';
import CommandPalette from '../ui/CommandPalette';
import KeyboardShortcutsModal from '../ui/KeyboardShortcutsModal';
import ToastContainer from '../ui/ToastContainer';

function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

      {/* Global Overlays: Command Palette, Keyboard Shortcuts, and Toasts */}
      <CommandPalette />
      <KeyboardShortcutsModal />
      <ToastContainer />

      <Header onToggleSidebar={() => setSidebarOpen((prev) => !prev)} />
      <div style={{
        display: 'flex',
        flex: 1,
        minHeight: 'calc(100vh - 64px)',
        position: 'relative',
      }}>
        {/* Mobile Backdrop Overlay */}
        {sidebarOpen && (
          <div
            className="sidebar-backdrop"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
            style={{
              position: 'fixed',
              inset: 0,
              backgroundColor: 'rgba(15, 23, 42, 0.5)',
              zIndex: 1035,
              backdropFilter: 'blur(2px)',
            }}
          />
        )}
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
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
