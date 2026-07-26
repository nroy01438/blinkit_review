import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        grade: {
          A: "#15803d",
          B: "#2563eb",
          C: "#b45309",
          D: "#b91c1c",
        },
      },
    },
  },
  plugins: [],
};
export default config;
