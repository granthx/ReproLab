import { Locale } from "./i18n";
import { Investigation, Claim, Evidence, Protocol, ProductionMeasurement, Evaluation, WorkflowRun } from "./api";

/**
 * Plain Words translation layer ("The Glass Box").
 * Transforms exact raw API records into clear, plain sentences for non-specialists.
 *
 * Rules:
 * 1. Never drop an underlying fact.
 * 2. Never invent a fact not present in the record.
 * 3. Clearly separate technical software execution from scientific truth.
 * 4. Explicitly label practice/synthetic framework tests.
 */

export function plainSourceKind(sourceKind: string, locale: Locale = "en"): string {
  if (sourceKind === "synthetic_framework_test") {
    return locale === "hi"
      ? "सिंथेटिक बेंचमार्क आधार (आंतरिक सत्यापन फिक्सचर)"
      : "Synthetic framework baseline test (internal benchmark fixture)";
  }
  if (sourceKind === "paper") {
    return locale === "hi"
      ? "प्रकाशित प्राथमिक शोध पत्र"
      : "Original published scientific paper";
  }
  return sourceKind;
}

export function plainVerdict(verdict: string, locale: Locale = "en"): { label: string; explanation: string } {
  switch (verdict) {
    case "reproduced":
      return {
        label: locale === "hi" ? "सफलतापूर्वक पुनरुत्पादित" : "Reproduced Successfully",
        explanation: locale === "hi"
          ? "स्वतंत्र परीक्षण में शोध पत्र का दावा सही साबित हुआ।"
          : "The independent test matched the claim made in the paper.",
      };
    case "disconfirmed":
      return {
        label: locale === "hi" ? "अपुष्ट (दावा गलत पाया गया)" : "Disconfirmed",
        explanation: locale === "hi"
          ? "परीक्षण में परिणाम शोध पत्र के दावे से काफी अलग पाया गया।"
          : "The independent test showed the paper's claim did not hold up.",
      };
    case "inconclusive":
      return {
        label: locale === "hi" ? "अनिर्णायक परिणाम" : "Inconclusive",
        explanation: locale === "hi"
          ? "डेटा या साक्ष्य पर्याप्त नहीं थे, इसलिए कोई पक्का निष्कर्ष नहीं निकाला जा सकता।"
          : "There was not enough data to be sure. The result remains open.",
      };
    case "execution_failed":
      return {
        label: locale === "hi" ? "सॉफ्टवेयर प्रक्रिया विफल" : "Process Failed (Not Disproven)",
        explanation: locale === "hi"
          ? "कंप्यूटर प्रोग्राम या प्रयोग समय सीमा या त्रुटि के कारण पूरा नहीं हो सका। इसका मतलब यह नहीं है कि दावा गलत है।"
          : "The computer program or container crashed or timed out. This means we could not check the claim, not that the paper is wrong.",
      };
    default:
      return {
        label: locale === "hi" ? "मूल्यांकन शेष" : "Not Assessed Yet",
        explanation: locale === "hi"
          ? "इस मामले का अभी अंतिम वैज्ञानिक मूल्यांकन नहीं किया गया है।"
          : "This case has not had an evaluation run yet.",
      };
  }
}

export function plainClaim(claim: Claim, locale: Locale = "en"): string {
  const dirWord = claim.metric_direction === "maximize"
    ? (locale === "hi" ? "अधिकतम" : "higher is better")
    : (locale === "hi" ? "न्यूनतम" : "lower is better");

  if (claim.reported_value !== null && claim.reported_value !== undefined) {
    const valPercent = (claim.reported_value * 100).toFixed(1);
    return locale === "hi"
      ? `शोध पत्र का दावा है कि ${claim.metric_name} का परिणाम ${valPercent}% होना चाहिए (${dirWord})।`
      : `The paper claims a score of ${valPercent}% for ${claim.metric_name} (${dirWord}).`;
  }
  return locale === "hi"
    ? `शोध पत्र में दावा किया गया है: "${claim.statement}", लेकिन कोई निश्चित संख्या नहीं दी गई है।`
    : `The paper claims: "${claim.statement}" (no exact number reported).`;
}

export function plainMeasurement(m: ProductionMeasurement, locale: Locale = "en"): string {
  const measuredPct = (m.value * 100).toFixed(1);
  const lowerPct = (m.interval_lower * 100).toFixed(1);
  const upperPct = (m.interval_upper * 100).toFixed(1);

  return locale === "hi"
    ? `स्वतंत्र प्रयोग में ${m.sample_size} उदाहरणों की जांच की गई और वास्तविक परिणाम ${measuredPct}% रहा। सांख्यिकीय रूप से हम 95% आश्वस्त हैं कि सही सीमा ${lowerPct}% से ${upperPct}% के बीच है।`
    : `In our independent test across ${m.sample_size} rows, the model achieved ${measuredPct}%. Because ${m.sample_size} rows is a sample, the honest 95% confidence range is ${lowerPct}% to ${upperPct}%.`;
}

export function plainProtocolStatus(protocol: Protocol, locale: Locale = "en"): string {
  if (protocol.status === "frozen") {
    return locale === "hi"
      ? `प्रोटोकॉल संस्करण ${protocol.version_number} स्थिर (Frozen) कर दिया गया है। निष्पक्षता बनाए रखने के लिए अब इसमें कोई बदलाव नहीं किया जा सकता।`
      : `Protocol version ${protocol.version_number} is frozen. To guarantee fairness, no one can change its rules now.`;
  }
  if (protocol.status === "approved") {
    return locale === "hi"
      ? `प्रोटोकॉल संस्करण ${protocol.version_number} स्वीकृत है और स्थिर (Freeze) किए जाने के लिए तैयार है।`
      : `Protocol version ${protocol.version_number} is approved and ready to be frozen before execution.`;
  }
  return locale === "hi"
    ? `प्रोटोकॉल संस्करण ${protocol.version_number} अभी प्रारंभिक प्रारूप (Draft) में है।`
    : `Protocol version ${protocol.version_number} is still being drafted.`;
}

export function plainWorkflowStatus(run: WorkflowRun, locale: Locale = "en"): string {
  if (run.status === "awaiting_human_review") {
    return locale === "hi"
      ? "कार्यप्रवाह रुका हुआ है। किसी प्रयोग को चलाने से पहले एक मानवीय समीक्षक द्वारा प्रोटोकॉल को सत्यापित करना अनिवार्य है।"
      : "The automated pipeline is paused at a human gate. A person must verify the protocol before any code can run.";
  }
  if (run.status === "completed") {
    return locale === "hi"
      ? "सभी 14 वैज्ञानिक चरणों ने अपना कार्य सफलतापूर्वक पूरा कर लिया है।"
      : "All 14 reproduction pipeline stages completed successfully.";
  }
  if (run.status === "blocked") {
    return locale === "hi"
      ? "कार्यप्रवाह अवरुद्ध है क्योंकि आवश्यक इनपुट या साक्ष्य अधूरा था।"
      : "The pipeline is blocked because required evidence or protocol details were missing.";
  }
  return locale === "hi"
    ? `कार्यप्रवाह की वर्तमान स्थिति: ${run.status}`
    : `Pipeline status: ${run.status.replace(/_/g, " ")}`;
}

