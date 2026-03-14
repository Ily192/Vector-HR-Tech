/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#37b1d3', // Topacio - Azul Vibrante
          secondary: '#262f3f', // Onix - Gris Oscuro
          turmalina: '#d337b1', // Acento Rosa
          jade: '#b1d337', // Acento Verde
          zafiro: '#3755d3', // Acento Azul Oscuro
        }
      },
      fontFamily: {
        sans: ['Poppins', 'sans-serif'], // Tipografía del Brand Book
      }
    },
  },
  plugins: [],
}
