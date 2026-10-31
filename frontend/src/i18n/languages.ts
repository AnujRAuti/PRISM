export interface LanguageOption {
  code: string;
  name: string;
  nativeName: string;
  script: string;
  isRtl?: boolean;
}

export const SUPPORTED_LANGUAGES: LanguageOption[] = [
  {
    code: 'en',
    name: 'English',
    nativeName: 'English',
    script: 'Latin',
  },
];

