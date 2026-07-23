import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

export type Language = 'zh' | 'en';

interface LanguageContextValue {
  language: Language;
  locale: string;
  setLanguage: (language: Language) => void;
  toggleLanguage: () => void;
  text: (zh: string, en: string) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => localStorage.getItem('language') === 'en' ? 'en' : 'zh');
  useEffect(() => {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.title = language === 'zh' ? 'TA Platform - 智能助教平台' : 'TA Platform - Smart Teaching Assistant';
  }, [language]);
  const setLanguage = (next: Language) => {
    setLanguageState(next);
    localStorage.setItem('language', next);
    document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en';
  };
  const value = useMemo<LanguageContextValue>(() => ({
    language,
    locale: language === 'zh' ? 'zh-CN' : 'en-US',
    setLanguage,
    toggleLanguage: () => setLanguage(language === 'zh' ? 'en' : 'zh'),
    text: (zh, en) => language === 'zh' ? zh : en,
  }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error('useLanguage must be used inside LanguageProvider');
  return context;
}

export function LanguageToggle({ className = '' }: { className?: string }) {
  const { language, toggleLanguage, text } = useLanguage();
  return <button type="button" className={`language-toggle ${className}`} onClick={toggleLanguage} title={text('切换到英文', 'Switch to Chinese')} aria-label={text('切换到英文', 'Switch to Chinese')}>
    {language === 'zh' ? 'EN' : '中文'}
  </button>;
}
