'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { SUPPORTED_LANGUAGES, LanguageOption } from './languages';
import { TRANSLATIONS } from './translations';

interface I18nContextType {
  language: string;
  currentLanguage: LanguageOption;
  setLanguage: (lang: string) => void;
  t: (key: string, defaultText?: string) => string;
  formatNumber: (num: number, options?: Intl.NumberFormatOptions) => string;
  formatDate: (date: Date | string, options?: Intl.DateTimeFormatOptions) => string;
  isRtl: boolean;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<string>('en');

  useEffect(() => {
    const saved = localStorage.getItem('eiil_language');
    if (saved && SUPPORTED_LANGUAGES.some(l => l.code === saved)) {
      setLanguageState(saved);
      applyLanguage(saved);
    }
  }, []);

  const applyLanguage = (code: string) => {
    const lang = SUPPORTED_LANGUAGES.find(l => l.code === code) || SUPPORTED_LANGUAGES[0];
    if (typeof document !== 'undefined') {
      document.documentElement.lang = lang.code;
      if (lang.isRtl) {
        document.documentElement.dir = 'rtl';
      } else {
        document.documentElement.dir = 'ltr';
      }
    }
  };

  const setLanguage = (code: string) => {
    setLanguageState(code);
    localStorage.setItem('eiil_language', code);
    applyLanguage(code);
  };

  const currentLanguage = SUPPORTED_LANGUAGES.find(l => l.code === language) || SUPPORTED_LANGUAGES[0];
  const isRtl = !!currentLanguage.isRtl;

  const t = (key: string, defaultText?: string): string => {
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

  const formatNumber = (num: number, options?: Intl.NumberFormatOptions): string => {
    try {
      const locale = language === 'en' ? 'en-IN' : language;
      return new Intl.NumberFormat(locale, options).format(num);
    } catch {
      return num.toLocaleString();
    }
  };

  const formatDate = (date: Date | string, options?: Intl.DateTimeFormatOptions): string => {
    try {
      const d = typeof date === 'string' ? new Date(date) : date;
      const locale = language === 'en' ? 'en-IN' : language;
      const defaultOptions: Intl.DateTimeFormatOptions = {
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

