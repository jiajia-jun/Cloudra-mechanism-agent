import { createRoot } from 'react-dom/client';
import App from './App';
import { I18nProvider } from './i18n';
import './styles.css';
import './glass.css';
import './emerald.css';
import './sidebar.css';

// Apply the saved appearance before React paints, avoiding a dark-theme flash.
try {
  document.documentElement.dataset.theme = localStorage.getItem('cloudra.theme') === 'emerald' ? 'emerald' : 'glass';
} catch {
  document.documentElement.dataset.theme = 'glass';
}

createRoot(document.getElementById('root')!).render(
  <I18nProvider>
    <App />
  </I18nProvider>,
);
