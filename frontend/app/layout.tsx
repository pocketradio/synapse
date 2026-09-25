import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Synapse",
  description: "Agentic knowledge engineering, with evidence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

