import type { Metadata } from "next";

export const metadata: Metadata = { title: "Site Signal" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
