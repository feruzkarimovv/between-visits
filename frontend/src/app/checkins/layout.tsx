import type { Metadata } from "next";

export const metadata: Metadata = { title: "Live check-in" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
