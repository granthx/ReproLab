"use client";

import React from "react";
import { AuthProvider } from "./lib/auth";
import { LensProvider } from "./lib/lens";
import { I18nProvider } from "./lib/i18n";
import { Shell } from "./components/Shell";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <LensProvider>
        <I18nProvider>
          <Shell>{children}</Shell>
        </I18nProvider>
      </LensProvider>
    </AuthProvider>
  );
}

