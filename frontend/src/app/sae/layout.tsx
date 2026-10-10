import type { Metadata } from "next";

export const metadata: Metadata = { title: "Serious-event report" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
