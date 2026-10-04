"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { RecentJobs } from "./RecentJobs";

const NAV_ITEMS = [
  {
    label: "Copywriting",
    href: "/copywriting",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
        <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
      </svg>
    ),
    soon: true,
  },
  {
    label: "Data Compilation",
    href: "/data-compilation",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
        <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
      </svg>
    ),
    soon: true,
  },
  {
    label: "Video Translation",
    href: "/",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
        <path fillRule="evenodd" d="M7 2a1 1 0 011 1v1h3a1 1 0 110 2H9.578a18.87 18.87 0 01-1.724 4.78c.29.354.596.696.914 1.026a1 1 0 11-1.44 1.389 21.034 21.034 0 01-.554-.6 19.098 19.098 0 01-3.107 3.567 1 1 0 01-1.334-1.49 17.087 17.087 0 003.13-3.733 18.992 18.992 0 01-1.487-3.754 1 1 0 111.934-.51c.31 1.173.704 2.316 1.179 3.402A17.27 17.27 0 007.576 7H3a1 1 0 110-2h4V3a1 1 0 011-1zm6 6a1 1 0 01.894.553l2.991 5.982a.869.869 0 01.02.037l.99 1.98a1 1 0 11-1.79.895L14.383 16h-4.764l-.724 1.447a1 1 0 11-1.788-.894l.99-1.98.019-.038 2.99-5.982A1 1 0 0113 8zm-1.382 6h2.764L13 11.236 11.618 14z" clipRule="evenodd" />
      </svg>
    ),
  },
  {
    label: "Video Editing",
    href: "/video-editing",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
        <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm3 2h6v4H7V5zm8 8v2h1v-2h-1zm-2-2H7v4h6v-4zm2 0h1V9h-1v2zm1-4V5h-1v2h1zM5 5H4v2h1V5zM4 7H3v2h1V7zm0 4H3v2h1v-2zm0 4v-2H3v2h1z" clipRule="evenodd" />
      </svg>
    ),
    soon: true,
  },
  {
    label: "Video Recording",
    href: "/video-recording",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
        <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
        <path d="M14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
      </svg>
    ),
    soon: true,
  },
  {
    label: "Publishing",
    href: "/publishing",
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
        <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
      </svg>
    ),
    soon: true,
  },
];

export function Navbar() {
  const pathname = usePathname();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/95 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4">
          <div className="h-14 flex items-center gap-6">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2 group flex-shrink-0">
              <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center">
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-white">
                  <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm3 2h6v4H7V5zm8 8v2h1v-2h-1zm-2-2H7v4h6v-4zm2 0h1V9h-1v2zm1-4V5h-1v2h1zM5 5H4v2h1V5zM4 7H3v2h1V7zm0 4H3v2h1v-2zm0 4v-2H3v2h1z" clipRule="evenodd" />
                </svg>
              </div>
              <span className="font-bold text-white text-sm tracking-tight group-hover:text-indigo-300 transition-colors">
                Video<span className="text-indigo-400">Factory</span>
              </span>
            </Link>

            {/* Divider */}
            <div className="h-5 w-px bg-zinc-800 flex-shrink-0" />

            {/* Nav links — hidden on small screens */}
            <nav className="hidden md:flex items-center gap-1 flex-1 overflow-x-auto scrollbar-none">
              {NAV_ITEMS.map((item) => {
                const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                return (
                  <div key={item.href} className="relative group flex-shrink-0">
                    {item.soon ? (
                      <button
                        disabled
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-600 cursor-not-allowed select-none"
                      >
                        {item.icon}
                        {item.label}
                        <span className="text-[10px] bg-zinc-800 border border-zinc-700 text-zinc-500 px-1.5 py-0.5 rounded-full leading-none">
                          Soon
                        </span>
                      </button>
                    ) : (
                      <Link
                        href={item.href}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                          isActive
                            ? "bg-indigo-600/20 text-indigo-300 border border-indigo-600/40"
                            : "text-zinc-400 hover:text-white hover:bg-zinc-800"
                        }`}
                      >
                        {item.icon}
                        {item.label}
                      </Link>
                    )}
                  </div>
                );
              })}
            </nav>

            {/* Right actions */}
            <div className="flex items-center gap-2 ml-auto flex-shrink-0">
              {/* Mobile menu toggle */}
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="md:hidden p-2 text-zinc-400 hover:text-white transition-colors"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                  <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
                </svg>
              </button>

              <button
                onClick={() => setHistoryOpen(!historyOpen)}
                className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                  historyOpen
                    ? "bg-indigo-600 border-indigo-600 text-white"
                    : "border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500"
                }`}
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                </svg>
                My Jobs
              </button>
            </div>
          </div>
        </div>

        {/* Mobile nav dropdown */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-zinc-800 bg-zinc-950 px-4 py-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return item.soon ? (
                <div
                  key={item.href}
                  className="flex items-center justify-between px-3 py-2 rounded-lg text-sm text-zinc-600"
                >
                  <span className="flex items-center gap-2">{item.icon}{item.label}</span>
                  <span className="text-[10px] bg-zinc-800 border border-zinc-700 text-zinc-500 px-1.5 py-0.5 rounded-full">Soon</span>
                </div>
              ) : (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? "bg-indigo-600/20 text-indigo-300" : "text-zinc-400 hover:text-white hover:bg-zinc-800"
                  }`}
                >
                  {item.icon}{item.label}
                </Link>
              );
            })}
          </div>
        )}
      </header>

      {/* My Jobs drawer */}
      {historyOpen && (
        <div className="fixed inset-0 z-40 flex justify-end" onClick={() => setHistoryOpen(false)}>
          <div
            className="relative w-80 bg-zinc-900 border-l border-zinc-800 h-full p-5 overflow-y-auto shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-white font-semibold">My Jobs</h2>
              <button
                onClick={() => setHistoryOpen(false)}
                className="text-zinc-500 hover:text-white transition-colors"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            <RecentJobs />
          </div>
        </div>
      )}
    </>
  );
}
