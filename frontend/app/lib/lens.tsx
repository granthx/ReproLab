"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export type Lens = "plain" | "technical";

type LensContextType = {
  lens: Lens;
  isPlain: boolean;
  isTechnical: boolean;
  setLens: (lens: Lens) => void;
  toggleLens: () => void;
};

const LENS_STORAGE_KEY = "reprolab_active_lens";

export function getStoredLens(): Lens {
  if (typeof window === "undefined") return "plain";
  try {
    const val = window.localStorage.getItem(LENS_STORAGE_KEY);
    return val === "technical" ? "technical" : "plain";
  } catch {
    return "plain";
  }
}

export function setStoredLens(lens: Lens): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LENS_STORAGE_KEY, lens);
  } catch {
    // Safely ignore storage quotas
  }
}

const LensContext = createContext<LensContextType>({
  lens: "plain",
  isPlain: true,
  isTechnical: false,
  setLens: () => {},
  toggleLens: () => {},
});

export function LensProvider({ children }: { children: React.ReactNode }) {
  const [lens, setLensState] = useState<Lens>("plain");

  useEffect(() => {
    setLensState(getStoredLens());
  }, []);

  const setLens = (newLens: Lens) => {
    setLensState(newLens);
    setStoredLens(newLens);
  };

  const toggleLens = () => {
    const next = lens === "plain" ? "technical" : "plain";
    setLens(next);
  };

  return (
    <LensContext.Provider
      value={{
        lens,
        isPlain: lens === "plain",
        isTechnical: lens === "technical",
        setLens,
        toggleLens,
      }}
    >
      {children}
    </LensContext.Provider>
  );
}

export function useLens(): LensContextType {
  return useContext(LensContext);
}
