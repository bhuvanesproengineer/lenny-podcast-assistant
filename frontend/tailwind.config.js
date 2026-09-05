/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#0F0F0F",
        sidebar: "#171717",
        card: "#212121",
        surface: {
          base: "#0F0F0F",
          card: "#171717",
          elevated: "#212121",
          hover: "#262626",
          border: "#2A2A2A",
        },
        border: "#2A2A2A",
        "border-subtle": "#222222",
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          DEFAULT: "#3b82f6",
          hover: "#60a5fa",
        },
        accent: {
          blue: "#3b82f6",
          "blue-hover": "#60a5fa",
          cyan: "#06b6d4",
          emerald: "#10b981",
          purple: "#8b5cf6",
        },
        muted: "#9CA3AF",
        "text-main": "#F3F4F6",
        "text-muted": "#9CA3AF",
        "text-secondary": "#9CA3AF",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Menlo",
          "Monaco",
          "Courier New",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 4px 20px -2px rgba(0, 0, 0, 0.5)",
        artifact: "0 10px 40px -10px rgba(0, 0, 0, 0.7)",
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
  ],
};
