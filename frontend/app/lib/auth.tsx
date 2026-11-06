"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { API_URL, api } from "./api";

export type UserRole = "viewer" | "operator" | "admin";

export type UserInfo = {
  username: string;
  role: UserRole;
  authenticated: boolean;
};

export const STANDARD_TOKENS: Record<UserRole, { token: string; label: string; desc: string }> = {
  viewer: {
    token: "reprolab-viewer-token",
    label: "Peer Reviewer / Viewer",
    desc: "Read-only audit access to all cases, evidence, protocols, sandbox logs, and statistical evaluations.",
  },
  operator: {
    token: "reprolab-operator-token",
    label: "Researcher",
    desc: "Full research capability: paper intake, claim extraction, protocol authoring, and execution runs.",
  },
  admin: {
    token: "reprolab-admin-token",
    label: "Principal Investigator (PI)",
    desc: "Full laboratory authority: all research actions plus diagnostics, evaluation sign-offs, and backups.",
  },
};

const STORAGE_KEY = "reprolab_auth_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY) || STANDARD_TOKENS.operator.token;
  } catch {
    return STANDARD_TOKENS.operator.token;
  }
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Safely ignore storage quotas or restricted browsing modes
  }
}

type AuthContextType = {
  user: UserInfo | null;
  token: string | null;
  role: UserRole;
  loading: boolean;
  canMutate: boolean;
  isAdmin: boolean;
  loginAs: (role: UserRole) => Promise<void>;
  setCustomToken: (token: string) => Promise<void>;
  signOut: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  role: "viewer",
  loading: true,
  canMutate: false,
  isAdmin: false,
  loginAs: async () => {},
  setCustomToken: async () => {},
  signOut: () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (activeToken: string | null) => {
    try {
      const headers: Record<string, string> = {};
      if (activeToken) {
        headers["Authorization"] = `Bearer ${activeToken}`;
      }
      const res = await fetch(`${API_URL}/auth/me`, { headers, cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setUser({
          username: data.username || "operator",
          role: (data.role as UserRole) || "operator",
          authenticated: Boolean(data.authenticated),
        });
      } else {
        // Fallback for when backend has auth disabled or returns unexpected status
        setUser({
          username: activeToken ? "active_user" : "guest",
          role: "operator",
          authenticated: Boolean(activeToken),
        });
      }
    } catch {
      // Backend offline or unreachable
      setUser({
        username: "local_operator",
        role: "operator",
        authenticated: true,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialToken = getStoredToken();
    setToken(initialToken);
    void fetchUser(initialToken);
  }, [fetchUser]);

  const loginAs = async (role: UserRole) => {
    const newToken = STANDARD_TOKENS[role].token;
    setStoredToken(newToken);
    setToken(newToken);
    await fetchUser(newToken);
  };

  const setCustomToken = async (newToken: string) => {
    setStoredToken(newToken);
    setToken(newToken);
    await fetchUser(newToken);
  };

  const signOut = () => {
    setStoredToken(null);
    setToken(null);
    setUser({
      username: "anonymous_viewer",
      role: "viewer",
      authenticated: false,
    });
  };

  const role = user?.role || "viewer";
  const canMutate = role === "operator" || role === "admin";
  const isAdmin = role === "admin";

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        role,
        loading,
        canMutate,
        isAdmin,
        loginAs,
        setCustomToken,
        signOut,
        refreshUser: () => fetchUser(token),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  return useContext(AuthContext);
}
