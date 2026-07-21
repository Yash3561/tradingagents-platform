import { ReactNode, useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import StatusBar from "./StatusBar";
import VerifyEmailBanner from "./VerifyEmailBanner";
import GuidedTour from "../onboarding/GuidedTour";

interface ShellProps {
  children: ReactNode;
  onLogout?: () => void;
}

export default function Shell({ children, onLogout }: ShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-base">
      <Sidebar
        onLogout={onLogout}
        mobileOpen={mobileNavOpen}
        onMobileClose={() => setMobileNavOpen(false)}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <Header onMenuClick={() => setMobileNavOpen(true)} />
        <VerifyEmailBanner />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          {children}
        </main>
        <StatusBar />
      </div>
      <GuidedTour />
    </div>
  );
}
