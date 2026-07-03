import { ReactNode } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import StatusBar from "./StatusBar";
import VerifyEmailBanner from "./VerifyEmailBanner";

interface ShellProps {
  children: ReactNode;
  onLogout?: () => void;
}

export default function Shell({ children, onLogout }: ShellProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-base">
      <Sidebar onLogout={onLogout} />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <VerifyEmailBanner />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
        <StatusBar />
      </div>
    </div>
  );
}
