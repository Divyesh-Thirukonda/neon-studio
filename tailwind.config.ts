import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        shell: "#151515",
        panel: "#202123",
        panel2: "#27292b",
        panel3: "#303236",
        line: "#42454a",
        paper: "#ece8dd",
        muted: "#a9a39a",
        drums: "#ff8d5c",
        bass: "#45d18e",
        chords: "#ffcd5a",
        lead: "#60c8f8",
        fx: "#d885ff"
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif"
        ]
      },
      boxShadow: {
        glow: "0 0 18px rgba(255, 224, 131, 0.28)"
      }
    }
  },
  plugins: []
};

export default config;
