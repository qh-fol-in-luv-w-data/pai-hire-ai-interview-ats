import type { Config } from 'tailwindcss';

export default {
  content: ['./*.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 950: '#071426', 900: '#0d1b35', 800: '#142744', 700: '#1c365c' },
        brand: { 50: '#eff6ff', 100: '#dbeafe', 500: '#1672f3', 600: '#075bd8', 700: '#0649ad', 800: '#0b3b82' },
        ink: { 950: '#111827', 700: '#374151', 500: '#6b7280', 300: '#d1d5db' },
      },
      boxShadow: {
        card: '0 8px 28px rgba(15, 23, 42, .07)',
        drawer: '-16px 0 48px rgba(15, 23, 42, .14)',
      },
      borderRadius: { '2xl': '1rem', '3xl': '1.5rem' },
    },
  },
  plugins: [],
} satisfies Config;
