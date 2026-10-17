import React, { createContext, useContext, useState, useEffect } from 'react';
import { SUPPORTED_LANGUAGES } from './languages';
import { TRANSLATIONS } from './translations';

const I18nContext = createContext();

export function I18nProvider({ children }) {
  const [language, setLanguageState] = useState('en');

  useEffect(() => {
    const saved = localStorage.getItem('eiil_language');
    if (saved && SUPPORTED_LANGUAGES.some(l => l.code === saved)) {
      setLanguageState(saved);
      applyLanguage(saved);
    }
  }, []);

  const applyLanguage = (code) => {
    const lang = SUPPORTED_LANGUAGES.find(l => l.code === code) || SUPPORTED_LANGUAGES[0];
    if (typeof document !== 'undefined') {
      document.documentElement.lang = lang.code;
      document.documentElement.dir = lang.isRtl ? 'rtl' : 'ltr';
    }
  };

  const setLanguage = (code) => {
    setLanguageState(code);
    localStorage.setItem('eiil_language', code);
    applyLanguage(code);
  };

  const currentLanguage = SUPPORTED_LANGUAGES.find(l => l.code === language) || SUPPORTED_LANGUAGES[0];
  const isRtl = !!currentLanguage?.isRtl;

  const t = (key, defaultText) => {
    const activeDict = TRANSLATIONS[language];
    if (activeDict && activeDict[key]) {
      return activeDict[key];
    }
    // Fallback to English
    const enDict = TRANSLATIONS.en;
    if (enDict && enDict[key]) {
      return enDict[key];
    }
    return defaultText || key;
  };

  const formatNumber = (num, options) => {
    try {
      const locale = language === 'en' ? 'en-IN' : language;
      return new Intl.NumberFormat(locale, options).format(num);
    } catch {
      return Number(num).toLocaleString();
    }
  };

  const formatDate = (date, options) => {
    try {
      const d = typeof date === 'string' ? new Date(date) : date;
      const locale = language === 'en' ? 'en-IN' : language;
      const defaultOptions = {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        ...options,
      };
      return new Intl.DateTimeFormat(locale, defaultOptions).format(d);
    } catch {
      return String(date);
    }
  };

  return (
    <I18nContext.Provider
      value={{
        language,
        currentLanguage,
        setLanguage,
        t,
        formatNumber,
        formatDate,
        isRtl,
      }}
    >
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
}

export default I18nContext;
