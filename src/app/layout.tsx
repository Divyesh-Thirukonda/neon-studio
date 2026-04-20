import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Neon Studio",
  description: "A local Next.js and Tailwind DAW workspace for Neon Solitude"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
