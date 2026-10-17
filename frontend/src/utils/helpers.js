// Utility functions for Proof-of-Action Frontend

/**
 * Format date for display
 * @param {string|Date} date - Date to format
 * @returns {string} Formatted date string
 */
export function formatDate(date) {
  const d = new Date(date);
  return d.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format file size for display
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
export function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Get risk level based on score
 * @param {number} score - Risk score (0-100)
 * @returns {Object} Risk level info
 */
export function getRiskLevel(score) {
  if (score < 25) return { label: 'Low', color: 'badge-success' };
  if (score < 50) return { label: 'Medium', color: 'badge-warning' };
  if (score < 75) return { label: 'High', color: 'badge-warning' };
  return { label: 'Critical', color: 'badge-danger' };
}

/**
 * Get integrity level based on score
 * @param {number} score - Integrity score (0-100)
 * @returns {Object} Integrity level info
 */
export function getIntegrityLevel(score) {
  if (score < 25) return { label: 'Very Low', color: 'badge-danger' };
  if (score < 50) return { label: 'Low', color: 'badge-warning' };
  if (score < 75) return { label: 'Medium', color: 'badge-info' };
  if (score < 90) return { label: 'High', color: 'badge-success' };
  return { label: 'Very High', color: 'badge-success' };
}

/**
 * Truncate text with ellipsis
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated text
 */
export function truncateText(text, maxLength = 100) {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
}

/**
 * Get user role label
 * @param {string} role - User role string
 * @returns {string} Formatted role label
 */
export function getUserRoleLabel(role) {
  const roleMap = {
    citizen: 'Citizen',
    reviewer: 'Reviewer',
    supervisor: 'Supervisor',
    admin: 'Administrator',
  };
  return roleMap[role] || role;
}

/**
 * Get status badge color
 * @param {string} status - Status string
 * @returns {string} Bootstrap badge class
 */
export function getStatusColor(status) {
  const colorMap = {
    pending: 'badge-warning',
    approved: 'badge-success',
    rejected: 'badge-danger',
    flagged: 'badge-danger',
    active: 'badge-success',
    completed: 'badge-info',
    draft: 'badge-secondary',
    'under-review': 'badge-warning',
  };
  return colorMap[status.toLowerCase()] || 'badge-secondary';
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Validate email format
 * @param {string} email - Email to validate
 * @returns {boolean} True if valid email
 */
export function validateEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email);
}

/**
 * Generate random ID for mock data
 * @returns {string} Random ID
 */
export function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

/**
 * Get Indian states list
 * @returns {Array} List of Indian states
 */
export function getIndianStates() {
  return [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
    'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
    'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
    'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
    'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
    'Uttar Pradesh', 'Uttarakhand', 'West Bengal'
  ];
}

/**
 * Capitalize first letter
 * @param {string} str - String to capitalize
 * @returns {string} Capitalized string
 */
export function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}
