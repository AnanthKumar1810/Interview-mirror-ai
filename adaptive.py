"""Bounded, explainable adaptive second question (with localized safe fallbacks)."""
from __future__ import annotations

# Questions are intentionally curated to avoid unconstrained or hallucinated prompts.
# 'concepts' here are the signals used to score the *follow-up*, not the first question.
FOLLOWUPS = {
    "agentic": {
        "evidence": {
            "en-IN": "What test result shows that your agent's changes were reliable? Describe one failure and how you verified it.",
            "te-IN": "మీ AI ఏజెంట్ మార్పులు నమ్మదగినవని ఏ పరీక్ష ఫలితం చూపించింది? ఒక వైఫల్యం, దాన్ని ఎలా ధృవీకరించారో చెప్పండి.",
            "hi-IN": "कौन-सा परीक्षण परिणाम दिखाता है कि आपके एजेंट के बदलाव भरोसेमंद थे? एक विफलता और उसकी जाँच बताइए।",
            "concepts": [("test evidence", ["test", "benchmark", "verified", "assert", "పరీక్ష", "ధృవ", "परीक्षण", "जांच"]),
                         ("failure example", ["fail", "bug", "regression", "error", "వైఫల", "లోప", "विफल", "त्रुटि"]),
                         ("reliability result", ["result", "passed", "rate", "cases", "ఫలిత", "సఫల", "परिणाम"])],
        },
        "technical": {
            "en-IN": "Describe one tool your agent can call, and explain the specific permission or validation rule that constrains it.",
            "te-IN": "మీ ఏజెంట్ ఉపయోగించే ఒక టూల్, దానికి వర్తించే అనుమతి లేదా ధృవీకరణ నియమాన్ని వివరించండి.",
            "hi-IN": "अपने एजेंट का एक टूल बताइए और उसके लिए कौन-सा अनुमति या जाँच नियम है, समझाइए।",
            "concepts": [("agent tool", ["tool", "api", "function", "టూల్", "టూల", "टूल"]),
                         ("approval / permission", ["approv", "permission", "human", "అనుమతి", "మానవ", "अनुमति", "मंजूरी"]),
                         ("validation step", ["validat", "test", "sandbox", "పరీక్ష", "नियंत्र", "परीक्षण"])],
        },
        "clarity": {
            "en-IN": "Walk through one agent run step by step: its input, tool action, and final validation result.",
            "te-IN": "ఒక ఏజెంట్ రన్‌ను దశల వారీగా వివరించండి: ఇన్‌పుట్, టూల్ చర్య, చివరి పరీక్ష ఫలితం.",
            "hi-IN": "एक एजेंट रन को क्रम से समझाइए: इनपुट, टूल कार्रवाई और अंतिम परीक्षण परिणाम।",
            "concepts": [("input", ["input", "request", "ఇన్‌పుట్", "अनुरोध", "इनपुट"]),
                         ("tool action", ["tool", "edit", "call", "టూల్", "మార్పు", "टूल"]),
                         ("validation result", ["test", "validat", "result", "పరీక్ష", "ఫలిత", "परीक्षण", "परिणाम"])],
        },
        "tradeoff": {
            "en-IN": "What alternative agent design did you reject, and what reliability trade-off drove your decision?",
            "te-IN": "ఏ ప్రత్యామ్నాయ ఏజెంట్ డిజైన్‌ను మీరు ఎంచుకోలేదు? నమ్మకత్వం విషయంలో ఏ నిర్ణయ కారణం ఉంది?",
            "hi-IN": "आपने कौन-सा वैकल्पिक एजेंट डिज़ाइन छोड़ा, और विश्वसनीयता का कौन-सा समझौता निर्णायक था?",
            "concepts": [("alternative", ["alternative", "instead", "versus", "ప్రత్యామ్నా", "विकल्प"]),
                         ("trade-off", ["trade", "cost", "latency", "complex", "ఖర్చు", "వేగ", "समझौता", "लागत"]),
                         ("reliability", ["reliab", "test", "validat", "నమ్మక", "పరీక్ష", "भरोसे", "परीक्षण"])],
        },
    },
    "ai": {
        "evidence": {
            "en-IN": "Which evaluation metric or baseline supports the result you reported for your model?",
            "te-IN": "మీ మోడల్ ఫలితాన్ని సమర్థించే మెట్రిక్ లేదా బేస్‌లైన్ ఏమిటి?",
            "hi-IN": "आपके मॉडल के परिणाम का समर्थन कौन-सा मूल्यांकन मेट्रिक या बेसलाइन करता है?",
            "concepts": [("metric", ["metric", "precision", "recall", "accuracy", "qwk", "మెట్రిక్", "ఖచ్చిత", "मूल्यांकन"]),
                         ("baseline", ["baseline", "compar", "previous", "బేస్‌లైన్", "పోల్చ", "बेसलाइन", "तुलना"]),
                         ("result", ["result", "score", "improv", "ఫలిత", "परिणाम"])],
        },
        "technical": {
            "en-IN": "Describe the dataset, model approach, and validation method you used in the project.",
            "te-IN": "మీ ప్రాజెక్ట్‌లో డేటాసెట్, మోడల్ విధానం, ధృవీకరణ పద్ధతి గురించి చెప్పండి.",
            "hi-IN": "अपने प्रोजेक्ट का डेटासेट, मॉडल तरीका और वैलिडेशन विधि बताइए।",
            "concepts": [("dataset", ["dataset", "data", "డేటా", "डेटा"]),
                         ("model", ["model", "architecture", "మోడల్", "मॉडल"]),
                         ("validation", ["test", "validat", "split", "పరీక్ష", "परीक्षण"])],
        },
        "clarity": {
            "en-IN": "Explain the ML pipeline in order: data preparation, training, and evaluation.",
            "te-IN": "మీ ML పైప్‌లైన్‌ను క్రమంగా చెప్పండి: డేటా సిద్ధం, శిక్షణ, మూల్యాంకనం.",
            "hi-IN": "ML पाइपलाइन को क्रम से बताइए: डेटा तैयारी, ट्रेनिंग और मूल्यांकन।",
            "concepts": [("preparation", ["data", "preprocess", "డేటా", "डेटा"]),
                         ("training", ["train", "model", "శిక్షణ", "प्रशिक्षण"]),
                         ("evaluation", ["metric", "test", "evaluat", "పరీక్ష", "मूल्यांकन"])],
        },
        "tradeoff": {
            "en-IN": "What model or preprocessing alternative did you consider, and why did you choose your final approach?",
            "te-IN": "మీరు ఏ ప్రత్యామ్నాయ మోడల్ లేదా ప్రీప్రాసెసింగ్ పద్ధతిని పరిశీలించారు? మీ నిర్ణయానికి కారణం ఏమిటి?",
            "hi-IN": "आपने कौन-सा वैकल्पिक मॉडल या प्रीप्रोसेसिंग तरीका सोचा और अंतिम तरीका क्यों चुना?",
            "concepts": [("alternative", ["alternative", "compar", "instead", "ప్రత్యామ్నా", "विकल्प"]),
                         ("model choice", ["model", "preprocess", "మోడల్", "मॉडल"]),
                         ("decision basis", ["because", "result", "metric", "ఎందుకంటే", "क्योंकि", "परिणाम"])],
        },
    },
    "software": {
        "evidence": {
            "en-IN": "Which failing test reproduced the bug, and what result proved your fix worked?",
            "te-IN": "బగ్‌ను చూపించిన పరీక్ష ఏది? మీ పరిష్కారం పని చేసిందని ఏ ఫలితం నిరూపించింది?",
            "hi-IN": "किस असफल परीक्षण ने बग दिखाया, और किस परिणाम से साबित हुआ कि आपका समाधान काम करता है?",
            "concepts": [("reproduction", ["reproduc", "fail", "test", "పరీక్ష", "వైఫల", "परीक्षण", "विफल"]),
                         ("change", ["fix", "edit", "changed", "సరి", "మార్పు", "सुधार"]),
                         ("passing test", ["pass", "verify", "test", "పరీక్ష", "సఫల", "सफल", "परीक्षण"])],
        },
        "technical": {
            "en-IN": "What was the root cause of the bug, which code change fixed it, and how did you test that change?",
            "te-IN": "బగ్ అసలు కారణం ఏమిటి, ఏ కోడ్ మార్పు దాన్ని సరిచేసింది, ఎలా పరీక్షించారు?",
            "hi-IN": "बग का मूल कारण क्या था, कौन-सा कोड बदलाव किया और उसे कैसे जाँचा?",
            "concepts": [("root cause", ["cause", "trace", "debug", "కారణ", "कारण"]),
                         ("code change", ["change", "fix", "edit", "మార్పు", "सुधार"]),
                         ("test", ["test", "validat", "పరీక్ష", "परीक्षण"])],
        },
        "clarity": {
            "en-IN": "Explain the debugging sequence step by step, from the failure to the verified fix.",
            "te-IN": "లోపం వచ్చినప్పటి నుంచి పరిష్కారం ధృవీకరణ వరకు ప్రతి దశను వివరించండి.",
            "hi-IN": "असफलता से सत्यापित समाधान तक डिबगिंग के हर चरण को क्रम से बताइए।",
            "concepts": [("failure", ["fail", "bug", "error", "లోప", "त्रुटि"]),
                         ("investigation", ["trace", "debug", "root", "కారణ", "जांच"]),
                         ("verification", ["test", "pass", "verify", "పరీక్ష", "परीक्षण"])],
        },
        "tradeoff": {
            "en-IN": "What other fix did you consider, and what testing or maintainability trade-off made you reject it?",
            "te-IN": "మీరు ఏ ఇతర పరిష్కారం ఆలోచించారు? పరీక్ష లేదా నిర్వహణ సమస్యల కారణంగా దాన్ని ఎందుకు ఎంచుకోలేదు?",
            "hi-IN": "आपने कौन-सा दूसरा समाधान सोचा, और परीक्षण या रखरखाव के किस समझौते के कारण उसे छोड़ा?",
            "concepts": [("alternative", ["alternative", "instead", "ప్రత్యామ్నా", "विकल्प"]),
                         ("trade-off", ["trade", "maintain", "time", "నాణ్యత", "సమయం", "समझौता"]),
                         ("test effect", ["test", "validat", "result", "పరీక్ష", "परीक्षण"])],
        },
    },
}

REASONS = {
    "technical": {
        "en-IN": "The previous answer omitted relevant technical concepts; let's clarify the mechanism.",
        "te-IN": "ముందటి సమాధానంలో కొన్ని సాంకేతిక అంశాలు లేవు; ఆ విధానాన్ని మరింత వివరించండి.",
        "hi-IN": "पिछले उत्तर में कुछ तकनीकी विवरण छूटे; आइए तरीका स्पष्ट करें.",
    },
    "evidence": {
        "en-IN": "The previous answer needs clearer testing evidence or a measurable result.",
        "te-IN": "ముందటి సమాధానంలో పరీక్ష ఆధారాలు లేదా కొలవగల ఫలితం మరింత స్పష్టంగా ఉండాలి.",
        "hi-IN": "पिछले उत्तर में जाँच के साक्ष्य या मापने योग्य परिणाम और स्पष्ट चाहिए.",
    },
    "clarity": {
        "en-IN": "The previous explanation could be clearer if it followed a step-by-step sequence.",
        "te-IN": "ముందటి వివరణ దశల వారీగా ఉంటే మరింత స్పష్టంగా ఉంటుంది.",
        "hi-IN": "पिछला विवरण चरणबद्ध होने पर अधिक स्पष्ट होगा.",
    },
    "tradeoff": {
        "en-IN": "You covered the basics; let's explore a design trade-off.",
        "te-IN": "మీరు ప్రాథమిక విషయాలను వివరించారు; ఇప్పుడు ఒక డిజైన్ నిర్ణయాన్ని పరిశీలిద్దాం.",
        "hi-IN": "आपने मूल बातें समझाईं; अब एक डिज़ाइन समझौते पर बात करें.",
    },
}


def select_followup(track: str, language: str, feedback: dict) -> tuple[dict, str, str]:
    """Return question metadata, transparent selection reason and chosen focus."""
    d = feedback["dimensions"]
    if d["technical_coverage"] < 20:
        focus = "technical"
    elif d["evidence"] < 12:
        focus = "evidence"
    elif d["clarity"] < 11:
        focus = "clarity"
    else:
        focus = "tradeoff"
    item = FOLLOWUPS[track][focus]
    return item, REASONS[focus][language], focus
