// theme.js - Shared theme toggle functionality
(function() {
  'use strict';

  // =============== THEME TOGGLE ===============
  function initThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    const themeIcon = themeToggle.querySelector('.icon');
    const themeLabel = themeToggle.querySelector('.label');
    
    // Load saved theme preference or default to dark mode
    const savedTheme = localStorage.getItem('theme') || 'dark';
    
    function applyTheme(theme) {
      if (theme === 'dark') {
        document.body.classList.add('dark-mode');
        if (themeIcon) themeIcon.textContent = '🌙';
        if (themeLabel) themeLabel.textContent = 'Dark Mode';
      } else {
        document.body.classList.remove('dark-mode');
        if (themeIcon) themeIcon.textContent = '☀️';
        if (themeLabel) themeLabel.textContent = 'Light Mode';
      }
      localStorage.setItem('theme', theme);
    }
    
    // Apply saved theme on page load
    applyTheme(savedTheme);
    
    // Toggle theme on button click
    themeToggle.addEventListener('click', (e) => {
      e.preventDefault();
      const currentTheme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      applyTheme(newTheme);
    });
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeToggle);
  } else {
    initThemeToggle();
  }
})();
