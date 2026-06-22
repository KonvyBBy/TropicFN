/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        fontFamily: {
          manrope: ['Manrope', 'sans-serif'],
          space: ['Space Grotesk', 'sans-serif'],
        },
        colors: {
          background: '#0a0a0a',
          foreground: '#f5f5f5',
          muted: '#a1a1aa',
          'muted-foreground': '#71717a',
        },
      },
    },
    plugins: [],
  }