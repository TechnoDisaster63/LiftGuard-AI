import type { Metadata } from "next";
import { Archivo, Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./liftguard.css";
import { TopNav } from "@/components/layout/TopNav";

const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });
const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "LiftGuard AI",
  description: "Real-time movement analysis for injury prevention",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} ${geist.variable} ${geistMono.variable}`}>
      <body className="antialiased">
        <div className="min-h-screen flex flex-col">
          <TopNav />
          <main className="lg-main flex-1 px-10 pt-6 pb-14">{children}</main>
          <footer
            className="fixed bottom-0 left-0 right-0 flex justify-between px-10 py-3 lg-m lg-faint pointer-events-none"
            style={{ fontSize: 10, background: "linear-gradient(0deg, var(--lg-bg) 55%, transparent)" }}
          >
            <span>Real-time movement analysis · injury prevention</span>
            <span>Not a medical diagnosis</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
