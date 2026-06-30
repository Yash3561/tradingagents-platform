import { ReactNode } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import StatusBar from "./StatusBar";

interface ShellProps {
  children: ReactNode;
}

export default function Shell({ children }: ShellProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-base">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
        <StatusBar />
      </div>
    </div>
  );
}
