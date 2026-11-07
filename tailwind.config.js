/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // Identité « terminal » héritée de Cyber-hoot : verts phosphore sur fond nuit.
        // Contrastes vérifiés (AA) : phosphore-700 sur blanc 5,0:1 ; phosphore-300 sur nuit-900 11:1.
        phosphore: {
          50: "#effdf3", 100: "#d7f8e0", 300: "#86efac", 400: "#4ade80", 500: "#22c55e",
          600: "#16a34a", 700: "#15803d", 800: "#166534", 900: "#14532d",
        },
        nuit: { 950: "#07100a", 900: "#0d1a11", 800: "#13261a", 700: "#1f3a28" },
      },
      fontFamily: {
        mono: [
          "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "Liberation Mono", "monospace",
        ],
        sans: [
          "system-ui", "-apple-system", "Segoe UI", "Roboto", "Ubuntu", "Cantarell",
          "Noto Sans", "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
