import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  formatDate,
  formatFileSize,
  getRiskLevel,
  getIntegrityLevel,
  truncateText,
  getUserRoleLabel,
  getStatusColor,
  validateEmail,
  generateId,
  getIndianStates,
  capitalize
} from '../src/utils/helpers.js';

describe('Utility Functions & Formatters', () => {
  test('formatDate correctly formats ISO date strings', () => {
    const isoDate = '2024-02-15T10:30:00Z';
    const formatted = formatDate(isoDate);
    assert.ok(typeof formatted === 'string');
    assert.ok(formatted.includes('2024'));
  });

  test('formatFileSize correctly calculates units', () => {
    assert.equal(formatFileSize(0), '0 Bytes');
    assert.equal(formatFileSize(1024), '1 KB');
    assert.equal(formatFileSize(1024 * 1024 * 2.5), '2.5 MB');
    assert.equal(formatFileSize(1024 * 1024 * 1024 * 1.2), '1.2 GB');
  });

  test('getRiskLevel returns correct risk classification and colors', () => {
    const low = getRiskLevel(15);
    assert.equal(low.label, 'Low');
    assert.equal(low.color, 'badge-success');

    const med = getRiskLevel(40);
    assert.equal(med.label, 'Medium');
    assert.equal(med.color, 'badge-warning');

    const high = getRiskLevel(65);
    assert.equal(high.label, 'High');

    const critical = getRiskLevel(85);
    assert.equal(critical.label, 'Critical');
    assert.equal(critical.color, 'badge-danger');
  });

  test('getIntegrityLevel returns correct integrity scores', () => {
    assert.equal(getIntegrityLevel(10).label, 'Very Low');
    assert.equal(getIntegrityLevel(35).label, 'Low');
    assert.equal(getIntegrityLevel(65).label, 'Medium');
    assert.equal(getIntegrityLevel(85).label, 'High');
    assert.equal(getIntegrityLevel(95).label, 'Very High');
  });

  test('truncateText truncates with ellipsis when length exceeded', () => {
    assert.equal(truncateText('Hello World', 20), 'Hello World');
    assert.equal(truncateText('This is a longer description text', 10), 'This is a ...');
    assert.equal(truncateText('', 10), '');
  });

  test('getUserRoleLabel translates system roles into human-readable titles', () => {
    assert.equal(getUserRoleLabel('citizen'), 'Citizen');
    assert.equal(getUserRoleLabel('reviewer'), 'Reviewer');
    assert.equal(getUserRoleLabel('supervisor'), 'Supervisor');
    assert.equal(getUserRoleLabel('admin'), 'Administrator');
    assert.equal(getUserRoleLabel('unknown_role'), 'unknown_role');
  });

  test('getStatusColor maps statuses to bootstrap classes', () => {
    assert.equal(getStatusColor('approved'), 'badge-success');
    assert.equal(getStatusColor('flagged'), 'badge-danger');
    assert.equal(getStatusColor('pending'), 'badge-warning');
    assert.equal(getStatusColor('completed'), 'badge-info');
  });

  test('validateEmail validates RFC-compliant email formats', () => {
    assert.equal(validateEmail('test@poa.gov.in'), true);
    assert.equal(validateEmail('officer.sharma@nic.in'), true);
    assert.equal(validateEmail('invalid-email-address'), false);
    assert.equal(validateEmail('@domain.com'), false);
    assert.equal(validateEmail('user@'), false);
  });

  test('generateId returns unique string identifiers', () => {
    const id1 = generateId();
    const id2 = generateId();
    assert.ok(typeof id1 === 'string' && id1.length > 0);
    assert.notEqual(id1, id2);
  });

  test('getIndianStates returns official list of Indian states', () => {
    const states = getIndianStates();
    assert.ok(Array.isArray(states));
    assert.ok(states.length >= 28);
    assert.ok(states.includes('Maharashtra'));
    assert.ok(states.includes('Gujarat'));
    assert.ok(states.includes('Rajasthan'));
  });

  test('capitalize capitalizes first character', () => {
    assert.equal(capitalize('proof'), 'Proof');
    assert.equal(capitalize('action'), 'Action');
  });
});
