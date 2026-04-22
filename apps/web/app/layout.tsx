import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "drug-cell-viz",
  description: "Drug-cell visualization platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <Providers>
          <div className="flex-1">{children}</div>
          <BottomNotice />
        </Providers>
      </body>
    </html>
  );
}

// End-of-page notice. It sits at the end of the document so the user reads it
// when they reach the bottom, but it does not float or track the viewport.
function BottomNotice() {
  return (
    <div className="border-t no-print" style={{ background: "rgba(217,119,6,0.10)" }}>
      <div className="max-w-[1600px] mx-auto px-6 md:px-8 py-3">
        <p className="text-center text-sm leading-relaxed">
          This helps you have better conversations with your care team. It does{" "}
          <strong>not</strong> tell you to change any medication.
        </p>
      </div>
    </div>
  );
}
