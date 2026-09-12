/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        leaf: { 50: "#f0f9ed", 100: "#dcefd5", 500: "#32824b", 700: "#1f5732", 900: "#10331c" },
        soil: { 50: "#fbf7ef", 200: "#ecdfc7", 700: "#795548" }
      },
      boxShadow: { card: "0 18px 45px rgba(31, 87, 50, 0.09)" }
    }
  },
  plugins: []
};
