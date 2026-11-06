"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export type Locale = "en" | "hi";

const LOCALE_STORAGE_KEY = "reprolab_locale";

export function getStoredLocale(): Locale {
  if (typeof window === "undefined") return "en";
  try {
    const val = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return val === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

export function setStoredLocale(loc: Locale): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, loc);
  } catch {
    // Safely ignore storage quotas
  }
}

export const DICTIONARY = {
  en: {
    // Brand & Topbar
    institute_title: "ReproLab",
    institute_subtitle: "AI Research Workbench",
    lens_plain: "Plain words",
    lens_technical: "Full record",
    lens_tooltip: "Switch between clear summary sentences and raw technical values",
    nav_home: "Overview",
    nav_investigations: "Investigations",
    nav_papers: "Paper Archive",
    nav_scientists: "Research Roles",
    nav_status: "System Status",

    // Roles & Auth
    role_viewer: "Viewer",
    role_operator: "Researcher",
    role_admin: "Principal Investigator",
    role_switch_prompt: "Switch Workspace Role",
    role_read_only_notice: "Peer reviewers and readers can inspect complete experiment records. Authorized researchers run reproduction pipelines.",
    role_sign_out: "Sign out",
    role_sign_in: "Sign in",

    // Verdicts
    verdict_reproduced: "Reproduced",
    verdict_disconfirmed: "Disconfirmed",
    verdict_inconclusive: "Inconclusive",
    verdict_execution_failed: "Execution Failed",
    verdict_not_assessed: "Not Assessed",

    // Badges & Statuses
    badge_practice_run: "Synthetic Benchmark Baseline",
    badge_literature_paper: "Published Literature Paper",
    badge_completed: "Completed",
    badge_running: "Running",
    badge_blocked: "Blocked",
    badge_abstained: "Abstained",
    badge_awaiting_human_review: "Awaiting Investigator Review",
    badge_frozen: "Frozen Protocol",
    badge_approved: "Approved Protocol",
    badge_draft: "Draft Protocol",

    // Sections & Headers
    section_open_cases: "Research Case Ledger",
    section_open_cases_sub: "Every investigation maintains an immutable, reproducible audit trail.",
    section_system_capabilities: "Workbench Infrastructure & Capabilities",
    section_the_rail: "Statistical Rail (Claimed vs Measured)",
    section_fingerprint: "Cryptographic Fingerprint",
    section_evidence_register: "Primary Literature Evidence Register",
    section_protocol_spec: "Frozen Research Protocol Specification",
    section_workflow_timeline: "14-Stage Computational Reproduction Pipeline",
    section_execution_attempts: "Hermetic Sandbox Execution Jobs",
    section_evaluation_gauges: "Empirical Reproducibility & Statistical Evaluation",

    // Actions & Buttons
    action_view_case: "Open Case Record →",
    action_view_all_cases: "View All Cases →",
    action_archive_paper: "Archive Paper PDF",
    action_uploading: "Uploading & Hashing…",
    action_create_investigation: "Start Investigation",
    action_add_claim: "Record Claim",
    action_add_evidence: "Record Evidence",
    action_record_review: "Record Manual Review",
    action_approve_protocol: "Approve Protocol",
    action_freeze_protocol: "Freeze Protocol",
    action_new_protocol_version: "Author Next Version",
    action_start_workflow: "Start Governed Workflow",
    action_approve_gate: "Approve & Continue Workflow",
    action_reject_gate: "Reject & Block Workflow",
    action_resume_workflow: "Resume Workflow",
    action_cancel_workflow: "Cancel Run",
    action_run_experiment: "Run Isolated Experiment",
    action_run_evaluation: "Evaluate Scientific Outcome",
    action_copy_hash: "Copy Full Hash",
    action_copied: "Copied!",
    action_retry: "Try Again",

    // Common Messages & Empty States
    empty_no_cases: "No investigations recorded yet. Start an investigation to begin.",
    empty_no_papers: "No papers archived yet. Upload a source PDF above.",
    empty_no_claims: "No claims extracted yet.",
    empty_no_evidence: "No evidence recorded yet.",
    empty_no_protocols: "No protocols drafted yet.",
    empty_no_measurements: "No production measurements recorded. Run an approved execution job to calculate trusted metrics.",
    loading: "Loading verified records from the institute…",
    error_connection: "Could not reach the ReproLab API. Check your connection or verify backend service is running.",
  },
  hi: {
    // Brand & Topbar
    institute_title: "रेप्रोलैब",
    institute_subtitle: "एआई शोध कार्यपीठ",
    lens_plain: "सरल शब्द",
    lens_technical: "पूर्ण विवरण",
    lens_tooltip: "सरल भाषा और पूर्ण तकनीकी विवरण के बीच बदलें",
    nav_home: "अवलोकन",
    nav_investigations: "जांच मामले",
    nav_papers: "शोध पत्र संग्रह",
    nav_scientists: "शोध भूमिकाएं",
    nav_status: "प्रणाली स्थिति",

    // Roles & Auth
    role_viewer: "समीक्षक (Viewer)",
    role_operator: "शोधकर्ता (Researcher)",
    role_admin: "मुख्य अन्वेषक (PI)",
    role_switch_prompt: "भूमिका बदलें",
    role_read_only_notice: "समीक्षक और पाठक संपूर्ण शोध रिकॉर्ड देख सकते हैं। अधिकृत शोधकर्ता ही पुनरुत्पादन कार्यप्रवाह चलाते हैं।",
    role_sign_out: "साइन आउट",
    role_sign_in: "साइन इन",

    // Verdicts
    verdict_reproduced: "पुनरुत्पादित (सफल)",
    verdict_disconfirmed: "अपुष्ट (असफल)",
    verdict_inconclusive: "अनिर्णायक",
    verdict_execution_failed: "प्रक्रिया विफल",
    verdict_not_assessed: "मूल्यांकन शेष",

    // Badges & Statuses
    badge_practice_run: "सिंथेटिक बेंचमार्क आधार",
    badge_literature_paper: "प्रकाशित शोध पत्र",
    badge_completed: "पूर्ण",
    badge_running: "प्रगति पर",
    badge_blocked: "अवरुद्ध",
    badge_abstained: "असहमत/रोका गया",
    badge_awaiting_human_review: "अन्वेषक समीक्षा की प्रतीक्षा",
    badge_frozen: "स्थिर प्रोटोकॉल (Frozen)",
    badge_approved: "स्वीकृत प्रोटोकॉल",
    badge_draft: "प्रारूप प्रोटोकॉल",

    // Sections & Headers
    section_open_cases: "सक्रिय शोध सूची",
    section_open_cases_sub: "प्रत्येक मामला एक अपरिवर्तनीय, पुनरुत्पादनीय ऑडिट रिकॉर्ड है।",
    section_system_capabilities: "शोध अवसंरचना व क्षमताएं",
    section_the_rail: "सांख्यिकीय पैमाना (दावा बनाम वास्तविक परिणाम)",
    section_fingerprint: "सुरक्षा पहचान पट्टी (Fingerprint)",
    section_evidence_register: "प्राथमिक शोध साक्ष्य रजिस्टर",
    section_protocol_spec: "अपरिवर्तनीय शोध प्रोटोकॉल",
    section_workflow_timeline: "14-चरणीय पुनरुत्पादन कार्यप्रवाह",
    section_execution_attempts: "सैंडबॉक्स परीक्षण प्रयास",
    section_evaluation_gauges: "प्रायोगिक पुनरुत्पादकता एवं सांख्यिकीय मूल्यांकन",

    // Actions & Buttons
    action_view_case: "मामला खोलें →",
    action_view_all_cases: "सभी मामले देखें →",
    action_archive_paper: "शोध पत्र अपलोड करें",
    action_uploading: "अपलोड एवं सुरक्षा जांच जारी…",
    action_create_investigation: "नई जांच शुरू करें",
    action_add_claim: "दावा जोड़ें",
    action_add_evidence: "साक्ष्य जोड़ें",
    action_record_review: "समीक्षा दर्ज करें",
    action_approve_protocol: "प्रोटोकॉल स्वीकार करें",
    action_freeze_protocol: "प्रोटोकॉल स्थिर करें (Freeze)",
    action_new_protocol_version: "नया संस्करण बनाएं",
    action_start_workflow: "कार्यप्रवाह शुरू करें",
    action_approve_gate: "स्वीकार करें और आगे बढ़ें",
    action_reject_gate: "अस्वीकार करें और रोकें",
    action_resume_workflow: "कार्यप्रवाह पुनः प्रारंभ करें",
    action_cancel_workflow: "रद्द करें",
    action_run_experiment: "सुरक्षित प्रयोग चलाएं",
    action_run_evaluation: "वैज्ञानिक मूल्यांकन करें",
    action_copy_hash: "पूर्ण कोड कॉपी करें",
    action_copied: "कॉपी हो गया!",
    action_retry: "पुनः प्रयास करें",

    // Common Messages & Empty States
    empty_no_cases: "अभी तक कोई जांच दर्ज नहीं है। शुरू करने के लिए नई जांच जोड़ें।",
    empty_no_papers: "कोई शोध पत्र संग्रहीत नहीं है। ऊपर दिए गए फॉर्म से पीडीएफ अपलोड करें।",
    empty_no_claims: "कोई दावा नहीं मिला।",
    empty_no_evidence: "कोई साक्ष्य दर्ज नहीं है।",
    empty_no_protocols: "कोई प्रोटोकॉल नहीं बनाया गया।",
    empty_no_measurements: "कोई माप दर्ज नहीं है। प्रमाणित आंकड़ों के लिए स्वीकृत प्रयोग चलाएं।",
    loading: "संस्थान से प्रमाणित रिकॉर्ड लोड किए जा रहे हैं…",
    error_connection: "रेप्रोलैब सर्वर से संपर्क नहीं हो सका। कृपया अपना इंटरनेट कनेक्शन जांचें।",
  },
};

type I18nContextType = {
  locale: Locale;
  setLocale: (loc: Locale) => void;
  toggleLocale: () => void;
  t: (key: keyof typeof DICTIONARY.en) => string;
};

const I18nContext = createContext<I18nContextType>({
  locale: "en",
  setLocale: () => {},
  toggleLocale: () => {},
  t: (key) => DICTIONARY.en[key] || String(key),
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    setLocaleState(getStoredLocale());
  }, []);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
    setStoredLocale(newLocale);
  };

  const toggleLocale = () => {
    setLocale(locale === "en" ? "hi" : "en");
  };

  const t = (key: keyof typeof DICTIONARY.en): string => {
    return DICTIONARY[locale]?.[key] || DICTIONARY.en[key] || String(key);
  };

  return (
    <I18nContext.Provider value={{ locale, setLocale, toggleLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextType {
  return useContext(I18nContext);
}
