import { createRoot } from 'react-dom/client';
import App from './App';
import { I18nProvider } from './i18n';
import { applyAppearance, readAppearance } from './appearance';
import './styles.css';
import './appearance.css';

applyAppearance(readAppearance());

createRoot(document.getElementById('root')!).render(
  <I18nProvider>
    <App />
  </I18nProvider>,
);
