import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens from the Figma design. Referenced as bg-success,
        // text-warning/70, border-info/30, etc. throughout the results view.
        success: "var(--success)",
        warning: "var(--warning)",
        info: "var(--info)",
        primary: "var(--primary)",
        "primary-foreground": "var(--primary-foreground)",
        card: "var(--card)",
        "card-foreground": "var(--card-foreground)",
        muted: "var(--muted)",
        "muted-foreground": "var(--muted-foreground)",
        border: "var(--border)",
        accent: "var(--accent)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
    },
  },
  plugins: [],
};

export default config;
