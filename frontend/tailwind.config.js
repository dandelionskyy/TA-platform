/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        accent: '#007bff',
        'accent-dark': '#3a96ff',
        sidebar: '#202123',
        'sidebar-dark': '#181818',
      },
    },
  },
  plugins: [],
};
