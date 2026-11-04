import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { SUPPORTED_LANGUAGES } from '../src/i18n/languages.ts';
import { TRANSLATIONS } from '../src/i18n/translations.ts';

describe('Multilingual Indian Language Support', () => {
  it('supports 12 languages including 11 official Indian languages and English', () => {
    assert.equal(SUPPORTED_LANGUAGES.length, 12);
    const codes = SUPPORTED_LANGUAGES.map((l) => l.code);
    const expectedCodes = ['en', 'hi', 'bn', 'ta', 'te', 'mr', 'gu', 'kn', 'ml', 'pa', 'or', 'ur'];
    assert.deepEqual(codes, expectedCodes);
  });

  it('marks Urdu as RTL and others as LTR', () => {
    const urdu = SUPPORTED_LANGUAGES.find((l) => l.code === 'ur');
    assert.equal(urdu?.isRtl, true);

    const hindi = SUPPORTED_LANGUAGES.find((l) => l.code === 'hi');
    assert.equal(!hindi?.isRtl, true);

    const tamil = SUPPORTED_LANGUAGES.find((l) => l.code === 'ta');
    assert.equal(!tamil?.isRtl, true);
  });

  it('verifies that every supported language has translations defined', () => {
    for (const lang of SUPPORTED_LANGUAGES) {
      assert.ok(TRANSLATIONS[lang.code], `Missing translation dictionary for ${lang.code}`);
      const keys = Object.keys(TRANSLATIONS[lang.code]);
      assert.ok(keys.length >= 70, `Language ${lang.code} should have full key set`);
      
      // Verify essential UI keys exist and are non-empty
      const essentialKeys = [
        'app_title',
        'nav_dashboard',
        'nav_queue',
        'nav_projects',
        'btn_create_project',
        'btn_refresh',
        'table_case',
        'table_origin',
        'table_status',
        'language_select',
      ];
      for (const key of essentialKeys) {
        assert.ok(
          TRANSLATIONS[lang.code][key],
          `Missing key "${key}" in language "${lang.code}"`
        );
        assert.ok(
          TRANSLATIONS[lang.code][key].trim().length > 0,
          `Empty key "${key}" in language "${lang.code}"`
        );
      }
    }
  });

  it('correctly maps Indian native script names', () => {
    const langMap = Object.fromEntries(SUPPORTED_LANGUAGES.map((l) => [l.code, l.nativeName]));
    assert.equal(langMap.hi, 'हिन्दी');
    assert.equal(langMap.bn, 'বাংলা');
    assert.equal(langMap.ta, 'தமிழ்');
    assert.equal(langMap.te, 'తెలుగు');
    assert.equal(langMap.mr, 'मराठी');
    assert.equal(langMap.gu, 'ગુજરાતી');
    assert.equal(langMap.kn, 'ಕನ್ನಡ');
    assert.equal(langMap.ml, 'മലയാളം');
    assert.equal(langMap.pa, 'ਪੰਜਾਬੀ');
    assert.equal(langMap.or, 'ଓଡ଼ିଆ');
    assert.equal(langMap.ur, 'اردو');
    assert.equal(langMap.en, 'English');
  });
});

