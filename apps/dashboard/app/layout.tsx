import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hyoka Dashboard",
  description: "Operational dashboard for agent reliability runs"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

