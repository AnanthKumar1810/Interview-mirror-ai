"""Bounded, explainable adaptive questioning with Socratic follow-up bank and 3 difficulty tiers.

Difficulty levels:
  - fundamentals: Conceptual foundations, core components, basic inputs/outputs.
  - applied: Practical implementation, concrete tool calls, error reproduction, testing evidence.
  - architecture: Scalability, production security, distributed systems, deep design trade-offs.
"""
from __future__ import annotations

import re
from typing import Any, Optional

DIFFICULTY_LEVELS = ["fundamentals", "applied", "architecture"]

# Socratic Question Bank across Tracks x Difficulty Tiers x Diagnostic Focuses
SOCRATIC_BANK = {
    "agentic": {
        "fundamentals": {
            "technical": {
                "en-IN": "Which specific tool does your agent use, and what validation rule ensures it does not fail?",
                "te-IN": "మీ ఏజెంట్ ఏ నిర్దిష్ట టూల్‌ను ఉపయోగిస్తుంది? అది విఫలం కాకుండా ఏ నియమం చూస్తుంది?",
                "hi-IN": "आपका एजेंट कौन-सा विशिष्ट टूल उपयोग करता है, और उसे विफल होने से कौन-सा नियम रोकता है?",
                "concepts": [
                    ("agent tool", ["tool", "api", "function", "టూల్", "టూల", "टूल"]),
                    ("input / validation", ["validat", "rule", "input", "పరిశీలన", "నియమం", "जांच", "नियम"]),
                    ("execution", ["call", "run", "action", "చర్య", "కార్య", "कार्रवाई", "रन"]),
                ],
            },
            "evidence": {
                "en-IN": "What basic test or check did you perform to confirm the agent completed its task?",
                "te-IN": "ఏజెంట్ తన పనిని పూర్తి చేసిందని నిర్ధారించడానికి మీరు ఏ ప్రాథమిక పరీక్ష చేశారు?",
                "hi-IN": "एजेंट ने अपना काम पूरा किया, यह पुष्टि करने के लिए आपने कौन-सी बुनियादी जाँच की?",
                "concepts": [
                    ("test check", ["test", "check", "verify", "పరీక్ష", "పరిశీలన", "जांच", "परीक्षण"]),
                    ("task outcome", ["result", "output", "done", "ఫలితం", "పూర్తి", "परिणाम"]),
                    ("observation", ["observed", "log", "saw", "చూశాను", "లాగ్", "देखा"]),
                ],
            },
            "clarity": {
                "en-IN": "State simply: what prompt or input starts the agent, and what exact output is produced?",
                "te-IN": "సరళంగా చెప్పండి: ఏజెంట్‌ను ఏ ప్రాంప్ట్ లేదా ఇన్‌పుట్ ప్రారంభిస్తుంది, ఏ అవుట్‌పుట్ వస్తుంది?",
                "hi-IN": "सरल शब्दों में बताइए: कौन-सा प्रॉम्प्ट या इनपुट एजेंट शुरू करता है, और क्या आउटपुट मिलता है?",
                "concepts": [
                    ("prompt / input", ["prompt", "input", "request", "ప్రాంప్ట్", "ఇన్‌పుట్", "प्रॉम्प्ट", "इनपुट"]),
                    ("tool execution", ["tool", "step", "call", "టూల్", "దశ", "टूल"]),
                    ("output", ["output", "result", "response", "అవుట్‌పుట్", "స్పందన", "आउटपुट"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What simpler alternative without an agent did you consider, and why did you choose an agent workflow?",
                "te-IN": "ఏజెంట్ లేకుండా ఏ సరళమైన ప్రత్యామ్నాయాన్ని ఆలోచించారు? ఏజెంట్ వర్క్‌ఫ్లోను ఎందుకు ఎంచుకున్నారు?",
                "hi-IN": "एजेंट के बिना आपने कौन-सा सरल वैकल्पिक तरीका सोचा था, और एजेंट वर्कफ़्लो क्यों चुना?",
                "concepts": [
                    ("alternative", ["alternative", "simple", "script", "ప్రత్యామ్నాయ", "విధానం", "विकल्प"]),
                    ("trade-off", ["trade", "manual", "auto", "నిర్ణయం", "ఖర్చు", "समझौता"]),
                    ("decision reason", ["because", "reason", "need", "ఎందుకంటే", "కారణం", "क्योंकि"]),
                ],
            },
        },
        "applied": {
            "technical": {
                "en-IN": "Describe one tool your agent can call, and explain the specific permission or validation rule that constrains it.",
                "te-IN": "మీ ఏజెంట్ ఉపయోగించే ఒక టూల్, దానికి వర్తించే అనుమతి లేదా ధృవీకరణ నియమాన్ని వివరించండి.",
                "hi-IN": "अपने एजेंट का एक टूल बताइए और उसके लिए कौन-सा अनुमति या जाँच नियम है, समझाइए।",
                "concepts": [
                    ("agent tool", ["tool", "api", "function", "టూల్", "టూల", "टूल"]),
                    ("approval / permission", ["approv", "permission", "human", "అనుమతి", "మానవ", "अनुमति", "मंजूरी"]),
                    ("validation step", ["validat", "test", "sandbox", "పరీక్ష", "పరిశీలన", "परीक्षण"]),
                ],
            },
            "evidence": {
                "en-IN": "What test result shows that your agent's changes were reliable? Describe one failure and how you verified it.",
                "te-IN": "మీ AI ఏజెంట్ మార్పులు నమ్మదగినవని ఏ పరీక్ష ఫలితం చూపించింది? ఒక వైఫల్యం, దాన్ని ఎలా ధృవీకరించారో చెప్పండి.",
                "hi-IN": "कौन-सा परीक्षण परिणाम दिखाता है कि आपके एजेंट के बदलाव भरोसेमंद थे? एक विफलता और उसकी जाँच बताइए।",
                "concepts": [
                    ("test evidence", ["test", "benchmark", "verified", "assert", "పరీక్ష", "ధృవ", "परीक्षण", "जांच"]),
                    ("failure example", ["fail", "bug", "regression", "error", "వైఫల", "లోప", "विफल", "त्रुटि"]),
                    ("reliability result", ["result", "passed", "rate", "cases", "ఫలిత", "సఫల", "परिणाम"]),
                ],
            },
            "clarity": {
                "en-IN": "Walk through one agent run step by step: its input, tool action, and final validation result.",
                "te-IN": "ఒక ఏజెంట్ రన్‌ను దశల వారీగా వివరించండి: ఇన్‌పుట్, టూల్ చర్య, చివరి పరీక్ష ఫలితం.",
                "hi-IN": "एक एजेंट रन को क्रम से समझाइए: इनपुट, टूल कार्रवाई और अंतिम परीक्षण परिणाम।",
                "concepts": [
                    ("input", ["input", "request", "ఇన్‌పుట్", "ప్రశ్న", "इनपुट"]),
                    ("tool action", ["tool", "edit", "call", "టూల్", "మార్పు", "टूल"]),
                    ("validation result", ["test", "validat", "result", "పరీక్ష", "ఫలిత", "परीक्षण", "परिणाम"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What alternative agent design did you reject, and what reliability trade-off drove your decision?",
                "te-IN": "ఏ ప్రత్యామ్నాయ ఏజెంట్ డిజైన్‌ను మీరు ఎంచుకోలేదు? నమ్మకత్వం విషయంలో ఏ నిర్ణయ కారణం ఉంది?",
                "hi-IN": "आपने कौन-सा वैकल्पिक एजेंट डिज़ाइन छोड़ा, और विश्वसनीयता का कौन-सा समझौता निर्णायक था?",
                "concepts": [
                    ("alternative", ["alternative", "instead", "versus", "ప్రత్యామ్నా", "విధానం", "विकल्प"]),
                    ("trade-off", ["trade", "cost", "latency", "complex", "ఖర్చు", "వేగ", "समझौता", "लागत"]),
                    ("reliability", ["reliab", "test", "validat", "నమ్మక", "పరీక్ష", "भरोसे", "परीक्षण"]),
                ],
            },
        },
        "architecture": {
            "technical": {
                "en-IN": "How do you enforce tool boundary isolation and secure the agent runtime against prompt injection in production?",
                "te-IN": "ప్రొడక్షన్‌లో ప్రాంప్ట్ ఇంజెక్షన్ నుంచి ఏజెంట్‌ను ఎలా కాపాడతారు మరియు టూల్ అనుమతులను ఎలా నియంత్రిస్తారు?",
                "hi-IN": "प्रोडक्शन में प्रॉम्प्ट इंजेक्शन से सुरक्षा और टूल एक्सेस सीमाओं को आप कैसे नियंत्रित करते हैं?",
                "concepts": [
                    ("tool isolation", ["tool", "sandbox", "isolat", "container", "టూల్", "నియంత్రణ", "टूल"]),
                    ("injection guard", ["inject", "prompt", "sanitiz", "guardrail", "భద్రత", "రక్షణ", "सुरक्षा"]),
                    ("production control", ["product", "permis", "auth", "విధానం", "అనుమతి", "नियंत्रण"]),
                ],
            },
            "evidence": {
                "en-IN": "What regression test suite or evaluation benchmarks prevent silent agent drift across model updates?",
                "te-IN": "మోడల్ నవీకరణలలో ఏజెంట్ లోపాలను నివారించడానికి ఏ ఆటోమేటెడ్ పరీక్షలు లేదా బెంచ్‌మార్క్ మెట్రిక్స్ వాడతారు?",
                "hi-IN": "मॉडल अपडेट के दौरान एजेंट बहाव रोकने के लिए आप कौन-सा रिग्रेशन परीक्षण सूट या बेंचमार्क उपयोग करते हैं?",
                "concepts": [
                    ("benchmark suite", ["benchmark", "eval", "suite", "పరీక్ష", "బెంచ్‌మార్క్", "परीक्षण"]),
                    ("drift detection", ["drift", "regress", "degrad", "లోపం", "మార్పు", "बहाव"]),
                    ("metric threshold", ["metric", "rate", "score", "మెట్రిక్", "శాతం", "स्कोर"]),
                ],
            },
            "clarity": {
                "en-IN": "Explain the multi-agent coordination protocol: state management, message serialization, and failure recovery.",
                "te-IN": "మల్టీ-ఏజెంట్ సమన్వయాన్ని వివరించండి: స్టేట్ నిర్వహణ, మెసేజ్ ఫార్మాట్, వైఫల్యాల రికవరీ ఎలా జరుగుతాయి?",
                "hi-IN": "मल्टी-एजेंट समन्वय समझाइए: स्टेट प्रबंधन, संदेश प्रोटोकॉल और विफलता सुधार कैसे काम करते हैं?",
                "concepts": [
                    ("coordination", ["coord", "multi", "orchestrat", "సమన్వయం", "ఆర్కెస్ట్రేషన్", "समन्वय"]),
                    ("state management", ["state", "store", "persist", "స్టేట్", "నిల్వ", "स्टेट"]),
                    ("recovery protocol", ["recover", "failover", "retry", "పునరుద్ధరణ", "తిరిగి", "सुधार"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What alternative orchestration framework did you evaluate, and how did latency versus autonomy guide your architecture?",
                "te-IN": "మీరు ఏ ప్రత్యామ్నాయ ఆర్కెస్ట్రేషన్ విధానాన్ని పరిశీలించారు? లేటెన్సీ మరియు ఆటోనమీ మధ్య నిర్ణయం ఎలా తీసుకున్నారు?",
                "hi-IN": "आपने कौन-सा वैकल्पिक आर्किटेक्चर सोचा और लेटेंसी बनाम स्वायत्तता के समझौते को कैसे साधा?",
                "concepts": [
                    ("alternative framework", ["alternative", "langchain", "autogen", "crew", "ప్రత్యామ్నాయ", "विकल्प"]),
                    ("trade-off", ["trade", "latency", "autonom", "నిర్ణయం", "వ్యవధి", "समझौता"]),
                    ("architecture rationale", ["architect", "scale", "overhead", "నిర్మాణం", "స్కేల్", "संरचना"]),
                ],
            },
        },
    },
    "ai": {
        "fundamentals": {
            "technical": {
                "en-IN": "What data did you feed into your model, and what specific output was it trained to predict?",
                "te-IN": "మీ మోడల్‌కు ఏ డేటా ఇచ్చారు, అది ఏ అవుట్‌పుట్‌ను అంచనా వేయడానికి శిక్షణ పొందింది?",
                "hi-IN": "आपने अपने मॉडल में कौन-सा डेटा दिया, और वह क्या आउटपुट देने के लिए प्रशिक्षित था?",
                "concepts": [
                    ("dataset", ["data", "dataset", "input", "డేటా", "डेटा"]),
                    ("model prediction", ["model", "predict", "output", "మోడల్", "అంచనా", "मॉडल"]),
                    ("training task", ["train", "task", "classif", "శిక్షణ", "పని", "प्रशिक्षण"]),
                ],
            },
            "evidence": {
                "en-IN": "What accuracy score or metric showed you that the model was learning during training?",
                "te-IN": "శిక్షణ సమయంలో మోడల్ నేర్చుకుంటోందని ఏ ఖచ్చితత్వ స్కోర్ లేదా మెట్రిక్ చూపించింది?",
                "hi-IN": "ट्रेनिंग के दौरान मॉडल सीख रहा था, यह किस सटीकता स्कोर या मेट्रिक ने दिखाया?",
                "concepts": [
                    ("accuracy metric", ["accura", "metric", "loss", "స్కోర్", "ఖచ్చితత్వ", "सटीकता"]),
                    ("score value", ["score", "val", "percent", "%", "విలువ", "నంబర్", "मान"]),
                    ("validation split", ["validat", "test", "split", "పరీక్ష", "పరిశీలన", "परीक्षण"]),
                ],
            },
            "clarity": {
                "en-IN": "Explain simply: how did you clean the raw data before feeding it into your model?",
                "te-IN": "సరళంగా వివరించండి: మోడల్‌కు ఇచ్చే ముందు ముడి డేటాను ఎలా శుభ్రం చేశారు?",
                "hi-IN": "सरल रूप से समझाइए: मॉडल में देने से पहले आपने कच्चे डेटा को कैसे साफ़ किया?",
                "concepts": [
                    ("raw data", ["raw", "data", "text", "డేటా", "ముడి", "डेटा"]),
                    ("cleaning step", ["clean", "null", "filter", "శుభ్రం", "ఫిల్టర్", "सफ़ाई"]),
                    ("prepared input", ["token", "feature", "input", "ఫీచర్", "ఇన్‌పుట్", "फ़ीचर"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What alternative baseline model did you test before choosing your final approach?",
                "te-IN": "చివరి విధానాన్ని ఎంచుకునే ముందు ఏ ప్రత్యామ్నాయ సాధారణ మోడల్‌ను పరీక్షించారు?",
                "hi-IN": "अंतिम दृष्टिकोण चुनने से पहले आपने कौन-सा वैकल्पिक बेसलाइन मॉडल जाँचा?",
                "concepts": [
                    ("alternative model", ["alternative", "baseline", "simple", "ప్రత్యామ్నాయ", "బేస్‌లైన్", "विकल्प"]),
                    ("comparison", ["compar", "versus", "vs", "పోల్చి", "తేడా", "तुलना"]),
                    ("choice reason", ["because", "better", "score", "ఎందుకంటే", "మెరుగ్గా", "क्योंकि"]),
                ],
            },
        },
        "applied": {
            "technical": {
                "en-IN": "Describe the dataset, model approach, and validation method you used in the project.",
                "te-IN": "మీ ప్రాజెక్ట్‌లో డేటాసెట్, మోడల్ విధానం, ధృవీకరణ పద్ధతి గురించి చెప్పండి.",
                "hi-IN": "अपने प्रोजेक्ट का डेटासेट, मॉडल तरीका और वैलिडेशन विधि बताइए।",
                "concepts": [
                    ("dataset", ["dataset", "data", "డేటా", "डेटा"]),
                    ("model", ["model", "architecture", "మోడల్", "मॉडल"]),
                    ("validation", ["test", "validat", "split", "పరీక్ష", "परीक्षण"]),
                ],
            },
            "evidence": {
                "en-IN": "Which evaluation metric or baseline supports the result you reported for your model?",
                "te-IN": "మీ మోడల్ ఫలితాన్ని సమర్థించే మెట్రిక్ లేదా బేస్‌లైన్ ఏమిటి?",
                "hi-IN": "आपके मॉडल के परिणाम का समर्थन कौन-सा मूल्यांकन मेट्रिक या बेसलाइन करता है?",
                "concepts": [
                    ("metric", ["metric", "precision", "recall", "accuracy", "qwk", "మెట్రిక్", "ఖచ్చిత", "मूल्यांकन"]),
                    ("baseline", ["baseline", "compar", "previous", "బేస్‌లైన్", "పోల్చ", "बेसलाइन", "तुलना"]),
                    ("result", ["result", "score", "improv", "ఫలిత", "పరిणाम"]),
                ],
            },
            "clarity": {
                "en-IN": "Explain the ML pipeline in order: data preparation, training, and evaluation.",
                "te-IN": "మీ ML పైప్‌లైన్‌ను క్రమంగా చెప్పండి: డేటా సిద్ధం, శిక్షణ, మూల్యాంకనం.",
                "hi-IN": "ML पाइपलाइन को क्रम से बताइए: डेटा तैयारी, ट्रेनिंग और मूल्यांकन।",
                "concepts": [
                    ("preparation", ["data", "preprocess", "డేటా", "डेटा"]),
                    ("training", ["train", "model", "శిక్షణ", "प्रशिक्षण"]),
                    ("evaluation", ["metric", "test", "evaluat", "పరీక్ష", "मूल्यांकन"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What model or preprocessing alternative did you consider, and why did you choose your final approach?",
                "te-IN": "మీరు ఏ ప్రత్యామ్నాయ మోడల్ లేదా ప్రీప్రాసెసింగ్ పద్ధతిని పరిశీలించారు? మీ నిర్ణయానికి కారణం ఏమిటి?",
                "hi-IN": "आपने कौन-सा वैकल्पिक मॉडल या प्रीप्रोसेसिंग तरीका सोचा और अंतिम तरीका क्यों चुना?",
                "concepts": [
                    ("alternative", ["alternative", "compar", "instead", "ప్రత్యామ్నా", "విధానం", "विकल्प"]),
                    ("model choice", ["model", "preprocess", "మోడల్", "మార్పు", "मॉडल"]),
                    ("decision basis", ["because", "result", "metric", "ఎందుకంటే", "ఫలితం", "क्योंकि", "परिणाम"]),
                ],
            },
        },
        "architecture": {
            "technical": {
                "en-IN": "How does your inference architecture handle latency budgets, GPU batching, and model quantization in production?",
                "te-IN": "ప్రొడక్షన్‌లో లేటెన్సీ బడ్జెట్, GPU బ్యాచింగ్, మోడల్ క్వాంటైజేషన్ ఎలా నిర్వహిస్తారు?",
                "hi-IN": "प्रोडक्शन में लेटेंसी बजट, GPU बैचिंग और मॉडल क्वांटाइजेशन आप कैसे संभालते हैं?",
                "concepts": [
                    ("latency budget", ["latency", "sla", "ms", "throughput", "లేటెన్సీ", "వేగం", "लेटेंसी"]),
                    ("serving optimization", ["batch", "quantiz", "tensorrt", "onnx", "ఆప్టిమైజ్", "క్వాంటైజేషన్", "बैचिंग"]),
                    ("gpu infrastructure", ["gpu", "memory", "cuda", "హార్డ్‌వేర్", "మెమరీ", "मेमोरी"]),
                ],
            },
            "evidence": {
                "en-IN": "What production monitoring detects online data distribution drift, and what threshold triggers retraining?",
                "te-IN": "డేటా డ్రిఫ్ట్‌ను గుర్తించడానికి ఏ మానిటరింగ్ ఉంది? మళ్లీ శిక్షణ ప్రారంభించడానికి ఏ పరిమితి ఉంది?",
                "hi-IN": "ऑनलाइन डेटा ड्रिफ्ट पकड़ने के लिए क्या निगरानी है, और दोबारा ट्रेनिंग के लिए कौन-सा थ्रेशोल्ड है?",
                "concepts": [
                    ("drift monitoring", ["drift", "distribut", "ks", "psi", "డ్రిఫ్ట్", "నిరీక్షణ", "ड्रिफ्ट"]),
                    ("retraining trigger", ["retrain", "pipelin", "trigger", "శిక్షణ", "ట్రిగ్గర్", "रीट्रेनिंग"]),
                    ("production telemetry", ["monitor", "alert", "log", "అలర్ట్", "లాగ్", "निगरानी"]),
                ],
            },
            "clarity": {
                "en-IN": "Explain the end-to-end MLOps lifecycle from feature store through canary deployment and observability.",
                "te-IN": "ఫీచర్ స్టోర్ నుండి కానరీ డిప్లాయ్‌మెంట్ మరియు అబ్జర్వబిలిటీ వరకు MLOps విధానాన్ని వివరించండి.",
                "hi-IN": "फ़ीचर स्टोर से लेकर कैनरी डिप्लॉयमेंट और ऑब्जर्वेबिलिटी तक MLOps चक्र समझाइए।",
                "concepts": [
                    ("feature store", ["feature", "store", "feast", "ఫీచర్", "డేటా", "फ़ीचर"]),
                    ("deployment strategy", ["canary", "shadow", "deploy", "కానరీ", "డిప్లాయ్", "डिप्लॉयमेंट"]),
                    ("observability", ["observ", "monitor", "telemetry", "టెలిమెట్రీ", "సమీక్ష", "निगरानी"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What trade-off between model parameter size and serving cost guided your production architecture?",
                "te-IN": "మోడల్ పరిమాణం మరియు సర్వింగ్ ఖర్చు మధ్య ఏ నిర్ణయం మీ ఆర్కిటెక్చర్‌ను నడిపించింది?",
                "hi-IN": "मॉडल आकार और सर्विंग लागत के किस समझौते ने आपके प्रोडक्शन आर्किटेक्चर को तय किया?",
                "concepts": [
                    ("parameter size", ["size", "param", "7b", "small", "పరిమాణం", "సైజు", "आकार"]),
                    ("cost trade-off", ["trade", "cost", "cloud", "ఖర్చు", "బడ్జెట్", "समझौता", "लागत"]),
                    ("serving trade-off", ["serv", "latenc", "through", "వేగం", "కెపాసిటీ", "सर्विंग"]),
                ],
            },
        },
    },
    "software": {
        "fundamentals": {
            "technical": {
                "en-IN": "What was the exact bug behavior, and which code file or function was responsible?",
                "te-IN": "బగ్ ఖచ్చితమైన ప్రవర్తన ఏమిటి? ఏ కోడ్ ఫైల్ లేదా ఫంక్షన్ దానికి కారణం?",
                "hi-IN": "बग का सटीक लक्षण क्या था, और कौन-सी कोड फ़ाइल या फ़ंक्शन ज़िम्मेदार थी?",
                "concepts": [
                    ("bug behavior", ["bug", "error", "fail", "బగ్", "లోపం", "बग"]),
                    ("code location", ["function", "file", "method", "ఫంక్షన్", "ఫైల్", "फ़ंक्शन"]),
                    ("cause", ["cause", "wrong", "null", "కారణం", "తప్పు", "कारण"]),
                ],
            },
            "evidence": {
                "en-IN": "How did you check that the bug was really fixed after making your change?",
                "te-IN": "మార్పు చేసిన తర్వాత బగ్ నిజంగా సరిదిద్దబడిందని మీరు ఎలా పరీక్షించారు?",
                "hi-IN": "बदलाव करने के बाद आपने कैसे जाँचा कि बग वास्तव में ठीक हो गया है?",
                "concepts": [
                    ("verification", ["test", "check", "run", "పరీక్ష", "రన్", "जांच"]),
                    ("fix confirmed", ["fix", "pass", "work", "సరి", "సఫలం", "सफल"]),
                    ("observation", ["log", "saw", "output", "అవుట్‌పుట్", "లాగ్", "देखा"]),
                ],
            },
            "clarity": {
                "en-IN": "Walk through your debugging steps simply: what failed first, what did you inspect, and what did you edit?",
                "te-IN": "మీ డీబగ్గింగ్ దశలను సరళంగా చెప్పండి: మొదట ఏమి విఫలమైంది, ఏమి పరిశీలించారు, ఏమి మార్చారు?",
                "hi-IN": "डिबगिंग चरणों को सरलता से बताइए: पहले क्या विफल हुआ, क्या जाँचा और क्या बदला?",
                "concepts": [
                    ("initial failure", ["fail", "error", "start", "వైఫల్యం", "మొదట", "विफलता"]),
                    ("inspection", ["inspect", "log", "print", "పరిశీలన", "లాగ్", "जांच"]),
                    ("edit", ["edit", "change", "fix", "మార్పు", "సరిదిద్దడం", "सुधार"]),
                ],
            },
            "tradeoff": {
                "en-IN": "Did you consider any temporary workaround before writing the proper fix?",
                "te-IN": "సరైన పరిష్కారం రాయడానికి ముందు మీరు ఏదైనా తాత్కాలిక మార్గాన్ని ఆలోచించారా?",
                "hi-IN": "उचित समाधान लिखने से पहले क्या आपने किसी अस्थायी विकल्प पर विचार किया था?",
                "concepts": [
                    ("workaround", ["workaround", "patch", "quick", "తాత్కాలిక", "త్వరిత", "विकल्प"]),
                    ("trade-off", ["trade", "clean", "proper", "సమస్య", "నిర్ణయం", "समझौता"]),
                    ("reason", ["because", "debt", "risk", "ఎందుకంటే", "ప్రమాదం", "क्योंकि"]),
                ],
            },
        },
        "applied": {
            "technical": {
                "en-IN": "What was the root cause of the bug, which code change fixed it, and how did you test that change?",
                "te-IN": "బగ్ అసలు కారణం ఏమిటి, ఏ కోడ్ మార్పు దాన్ని సరిచేసింది, ఎలా పరీక్షించారు?",
                "hi-IN": "बग का मूल कारण क्या था, कौन-सा कोड बदलाव किया और उसे कैसे जाँचा?",
                "concepts": [
                    ("root cause", ["cause", "trace", "debug", "కారణ", "మూలం", "कारण"]),
                    ("code change", ["change", "fix", "edit", "మార్పు", "సరి", "सुधार"]),
                    ("test", ["test", "validat", "పరీక్ష", "పరిశీలన", "परीक्षण"]),
                ],
            },
            "evidence": {
                "en-IN": "Which failing test reproduced the bug, and what result proved your fix worked?",
                "te-IN": "బగ్‌ను చూపించిన పరీక్ష ఏది? మీ పరిష్కారం పని చేసిందని ఏ ఫలితం నిరూపించింది?",
                "hi-IN": "किस असफल परीक्षण ने बग दिखाया, और किस परिणाम से साबित हुआ कि आपका समाधान काम करता है?",
                "concepts": [
                    ("reproduction", ["reproduc", "fail", "test", "పరీక్ష", "వైఫల", "परीक्षण", "विफल"]),
                    ("change", ["fix", "edit", "changed", "సరి", "మార్పు", "सुधार"]),
                    ("passing test", ["pass", "verify", "test", "పరీక్ష", "సఫల", "सफल", "परीक्षण"]),
                ],
            },
            "clarity": {
                "en-IN": "Explain the debugging sequence step by step, from the failure to the verified fix.",
                "te-IN": "లోపం వచ్చినప్పటి నుంచి పరిష్కారం ధృవీకరణ వరకు ప్రతి దశను వివరించండి.",
                "hi-IN": "असफलता से सत्यापित समाधान तक डिबगिंग के हर चरण को क्रम से बताइए।",
                "concepts": [
                    ("failure", ["fail", "bug", "error", "లోప", "వైఫల్యం", "त्रुटि"]),
                    ("investigation", ["trace", "debug", "root", "కారణ", "జాడ", "जांच"]),
                    ("verification", ["test", "pass", "verify", "పరీక్ష", "ధృవీకరణ", "परीक्षण"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What other fix did you consider, and what testing or maintainability trade-off made you reject it?",
                "te-IN": "మీరు ఏ ఇతర పరిష్కారం ఆలోచించారు? పరీక్ష లేదా నిర్వహణ సమస్యల కారణంగా దాన్ని ఎందుకు ఎంచుకోలేదు?",
                "hi-IN": "आपने कौन-सा दूसरा समाधान सोचा, और परीक्षण या रखरखाव के किस समझौते के कारण उसे छोड़ा?",
                "concepts": [
                    ("alternative", ["alternative", "instead", "ప్రత్యామ్నా", "విధానం", "विकल्प"]),
                    ("trade-off", ["trade", "maintain", "time", "నాణ్యత", "సమయం", "समझौता"]),
                    ("test effect", ["test", "validat", "result", "పరీక్ష", "పరిశీలన", "परीक्षण"]),
                ],
            },
        },
        "architecture": {
            "technical": {
                "en-IN": "How would you design idempotency, circuit breakers, and distributed retry policies to prevent cascade failures?",
                "te-IN": "కాస్కేడ్ వైఫల్యాలను నివారించడానికి ఐడెంపోటెన్సీ, సర్క్యూట్ బ్రేకర్లు, డిస్ట్రిబ్యూటెడ్ రిట్రై విధానాలను ఎలా డిజైన్ చేస్తారు?",
                "hi-IN": "कैस्केड विफलताओं को रोकने के लिए आप आइडेंपोटेंसी, सर्किट ब्रेकर और वितरित पुनः प्रयास कैसे डिज़ाइन करेंगे?",
                "concepts": [
                    ("idempotency", ["idempot", "dedup", "token", "కీ", "ఐడెంపోటెన్సీ", "आइडेंपोटेंसी"]),
                    ("circuit breaker", ["circuit", "break", "threshold", "సర్క్యూట్", "ఆపడం", "सर्किट"]),
                    ("retry / backoff", ["retry", "backoff", "jitter", "రిట్రై", "వ్యవధి", "बैकऑफ"]),
                ],
            },
            "evidence": {
                "en-IN": "What chaos engineering tests or load simulation metrics validate this system's high-availability SLA?",
                "te-IN": "వ్యవస్థ లభ్యత SLAని ధృవీకరించడానికి ఏ కేయాస్ పరీక్షలు లేదా లోడ్ సిమ్యులేషన్ మెట్రిక్స్ వాడతారు?",
                "hi-IN": "सिस्टम के SLA को मान्य करने के लिए आप कौन-से कैओस टेस्ट या लोड सिमुलेशन मेट्रिक्स उपयोग करते हैं?",
                "concepts": [
                    ("chaos / load test", ["chaos", "load", "stress", "k6", "కేయాస్", "లోడ్", "परीक्षण"]),
                    ("availability sla", ["sla", "99.", "uptime", "లభ్యత", "సమయం", "अपटाइम"]),
                    ("telemetry metrics", ["metric", "p99", "latency", "మెట్రిక్", "వేగం", "लेटेंसी"]),
                ],
            },
            "clarity": {
                "en-IN": "Explain the failover architecture: heartbeat detection, leader election, and distributed consensus.",
                "te-IN": "ఫెయిల్‌ఓవర్ విధానాన్ని వివరించండి: హార్ట్‌బీట్ గుర్తింపు, లీడర్ ఎన్నిక, డిస్ట్రిబ్యూటెడ్ కన్సెన్సస్.",
                "hi-IN": "फ़ेलओवर आर्किटेक्चर समझाइए: हार्टबीट डिटेक्शन, लीडर इलेक्शन और डिस्ट्रीब्यूटेड सर्वसम्मति।",
                "concepts": [
                    ("heartbeat", ["heartbeat", "health", "ping", "హార్ట్‌బీట్", "సిగ్నల్", "हार्टबीट"]),
                    ("consensus", ["raft", "paxos", "elect", "ఎన్నిక", "కన్సెన్సస్", "सर्वसम्मति"]),
                    ("failover", ["failover", "switch", "standby", "స్టాండ్‌బై", "మార్పిడి", "फ़ेलओवर"]),
                ],
            },
            "tradeoff": {
                "en-IN": "What trade-offs between consistency and availability (CAP theorem) determined your storage and replication architecture?",
                "te-IN": "కన్సిస్టెన్సీ మరియు అవైలబిలిటీ మధ్య ఏ నిర్ణయం మీ నిల్వ మరియు రెప్లికేషన్ డిజైన్‌ను నిర్ణయించింది?",
                "hi-IN": "स्थिरता बनाम उपलब्धता (CAP प्रमेय) के किस समझौते ने आपके स्टोरेज और प्रतिकृति आर्किटेक्चर को तय किया?",
                "concepts": [
                    ("cap theorem", ["cap", "consisten", "availab", "కన్సిస్టెన్సీ", "లభ్యత", "संगति"]),
                    ("storage trade-off", ["trade", "sync", "async", "నిర్ణయం", "సమయం", "समझौता"]),
                    ("replication choice", ["replicat", "eventual", "quorum", "రెప్లికేషన్", "కోరం", "रेप्लिकेशन"]),
                ],
            },
        },
    },
}

# Backward compatible pointer to applied tier
FOLLOWUPS = {
    track: SOCRATIC_BANK[track]["applied"]
    for track in SOCRATIC_BANK
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
    "misconception": {
        "en-IN": "The previous answer contained a conceptual misconception; let's address the foundational mechanism.",
        "te-IN": "ముందటి సమాధానంలో ఒక ప్రాథమిక లోపం ఉంది; ఆ విధానాన్ని పునఃపరిశీలిద్దాం.",
        "hi-IN": "पिछले उत्तर में एक बुनियादी भ्रांति थी; आइए मूल प्रक्रिया स्पष्ट करें.",
    },
}


def select_followup(
    track: str,
    language: str,
    feedback: dict,
    level: str | None = None,
) -> tuple[dict, str, str]:
    """Return question metadata, transparent selection reason and chosen focus.

    Dynamically selects difficulty tier (fundamentals, applied, architecture)
    based on candidate performance if not explicitly pinned.
    Addresses misconceptions by grounding follow-ups in foundational concepts.
    """
    if track not in SOCRATIC_BANK:
        track = "agentic"

    d = feedback.get("dimensions", {})
    tech_cov = d.get("technical_coverage", 0)
    ev_score = d.get("evidence", 0)
    clar_score = d.get("clarity", 0)
    total_score = feedback.get("score", sum(d.values()))

    has_misconception = bool(feedback.get("risks") or feedback.get("risk_flags") or feedback.get("misconceptions"))

    if has_misconception:
        focus = "technical"
        if level not in DIFFICULTY_LEVELS:
            selected_level = "fundamentals"
        else:
            selected_level = level
    else:
        # Determine focus from dimension deficits
        if tech_cov < 20:
            focus = "technical"
        elif ev_score < 12:
            focus = "evidence"
        elif clar_score < 11:
            focus = "clarity"
        else:
            focus = "tradeoff"

        # Select difficulty tier
        if level not in DIFFICULTY_LEVELS:
            if total_score >= 75:
                selected_level = "architecture"
            elif total_score >= 35:
                selected_level = "applied"
            else:
                selected_level = "fundamentals"
        else:
            selected_level = level

    tier_bank = SOCRATIC_BANK[track].get(selected_level, SOCRATIC_BANK[track]["applied"])
    item = dict(tier_bank[focus])
    item["level"] = selected_level
    item["focus"] = focus
    item["question_type"] = "socratic"

    if has_misconception and "misconception" in REASONS:
        reason_text = REASONS["misconception"].get(language, REASONS["misconception"]["en-IN"])
    else:
        reason_text = REASONS.get(focus, {}).get(language, REASONS[focus]["en-IN"])

    return item, reason_text, focus


def generate_dynamic_followup(
    transcript: str,
    feedback: dict[str, Any],
    next_question_spec: dict[str, Any] | None,
    language: str = "en-IN",
    question_index: int = 0,
    track: str = "agentic",
) -> tuple[str, str]:
    """Dynamically formulate conversational acknowledgment and targeted follow-up.

    Reflects the candidate's exact response (acknowledging stated tools,
    trade-offs, or conceptual definitions) and bridges smoothly into the next question.
    """
    text = transcript.strip()
    lowered = text.lower()

    ack = ""
    # 1. Turn 0 -> Turn 1: Candidate Self-Introduction Acknowledgment
    if question_index == 0:
        name_match = re.search(r"\b(?:name is|myself|i am|i'm|this is)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", text, re.I)
        candidate_name = name_match.group(1).title() if name_match else ""
        if candidate_name.lower() in ("a", "an", "the", "student", "developer", "engineer"):
            candidate_name = ""

        college_match = re.search(r"\b(?:from|at|in|studying at|studying in)\s+([A-Za-z0-9\s]+?(?:College(?:\s+of\s+Engineering)?|University|Institute|School))\b", text, re.I)
        college = college_match.group(1).strip() if college_match else ""

        skills_found = [s for s in ("autonomous agents", "machine learning", "data science", "python", "ai", "docker", "fastapi", "react") if s in lowered]
        focus = skills_found[0] if skills_found else "software engineering"

        if language == "te-IN":
            name_str = f", {candidate_name}" if candidate_name else ""
            ack = f"పరిచయం చేసుకున్నందుకు ధన్యవాదాలు{name_str}. మీ సాంకేతిక నేపథ్యం మరియు {focus} పై మీ ఆసక్తిని తెలుసుకోవడం చాలా బాగుంది."
        elif language == "hi-IN":
            name_str = f", {candidate_name}" if candidate_name else ""
            ack = f"परिचय देने के लिए धन्यवाद{name_str}। आपकी पृष्ठभूमि और {focus} में आपकी रुचि के बारे में जानकर अच्छा लगा।"
        else:
            name_str = f", {candidate_name}" if candidate_name else ""
            college_str = f" at {college}" if college else ""
            ack = f"Thanks for introducing yourself{name_str}. Great to hear about your background{college_str} and your focus on {focus}."

    # 2. Technical Turns (Turn 1 -> Turn 2, Turn 2 -> Turn 3)
    else:
        # Check for Precision vs Recall specific trade-offs (as in the candidate's audio sample)
        if "precision" in lowered or "recall" in lowered:
            if "precision" in lowered and ("recall" not in lowered or any(w in lowered for w in ("prioritize precision", "lean toward precision", "focus on precision", "best", "exact", "fraud", "favor", "prefer"))):
                if language == "te-IN":
                    ack = "అర్థమైంది. ఖచ్చితమైన కేసులను మాత్రమే గుర్తించడానికి మీరు ప్రిసిషన్‌కు ప్రాధాన్యత ఇస్తున్నారు."
                elif language == "hi-IN":
                    ack = "समझ गया। आप सटीक मामलों को पकड़ने के लिए प्रिसिजन को प्राथमिकता दे रहे हैं।"
                else:
                    ack = "I hear you. You're leaning toward maximizing correctness, so flagged cases are truly fraud."
            elif "recall" in lowered and ("precision" not in lowered or any(w in lowered for w in ("prioritize recall", "lean toward recall", "catch every", "all fraud", "miss"))):
                if language == "te-IN":
                    ack = "అర్థమైంది. ఒక్క మోసాన్ని కూడా వదలకుండా పట్టుకోవడానికి మీరు రీకాల్‌కు ప్రాధాన్యత ఇస్తున్నారు."
                elif language == "hi-IN":
                    ack = "समझ गया। आप सभी संभावित मामलों को पकड़ने के लिए रिकॉल को प्राथमिकता दे रहे हैं।"
                else:
                    ack = "I hear you. You're leaning toward maximizing recall, ensuring no fraudulent cases are missed."
            else:
                if language == "te-IN":
                    ack = "అర్థమైంది. ప్రిసిషన్ అంటే ప్రిడిక్షన్ ఖచ్చితత్వం, రీకాల్ అంటే మొత్తం పాజిటివ్‌లను కవర్ చేయడం అని చెప్పారు."
                elif language == "hi-IN":
                    ack = "समझ गया। आप प्रिसिजन को भविष्यवाणी की शुद्धता और रिकॉल को कुल वास्तविक मामलों की कवरेज बता रहे हैं।"
                else:
                    ack = "Got it. You're pointing to precision as correctness of predicted positives, and recall as how many actual positives you capture."

        # Check for specific technologies mentioned in candidate answer
        elif any(t in lowered for t in ("docker", "container", "sandbox", "guardrail", "swe-bench", "fastapi", "pytorch", "transformers", "redis", "postgres", "queue", "cache", "asyncio")):
            tools_hit = [t for t in ("Docker", "container", "sandbox", "guardrail", "FastAPI", "PyTorch", "Redis", "asyncio") if t.lower() in lowered]
            matched_tool = tools_hit[0] if tools_hit else "your architecture"
            if language == "te-IN":
                ack = f"అర్థమైంది. మీ పరిష్కారంలో {matched_tool} వాడకం గురించి స్పష్టంగా వివరించారు."
            elif language == "hi-IN":
                ack = f"समझ गया। आपने अपने समाधान में {matched_tool} के उपयोग पर प्रकाश डाला।"
            else:
                ack = f"Got it. You highlighted using {matched_tool} for your technical pipeline."

        # Check for performance / metric / optimization mentioned
        elif any(m in lowered for m in ("percent", "%", "latency", "reduced", "improved", "faster", "scale", "hackathon", "winner", "award")):
            if language == "te-IN":
                ack = "చాలా బాగుంది. మీరు సాధించిన కొలవదగిన ఫలితాలు మరియు నిర్ణయాలు స్పష్టంగా ఉన్నాయి."
            elif language == "hi-IN":
                ack = "बहुत अच्छा। आपके द्वारा हासिल किए गए परिणाम और तकनीकी निर्णय स्पष्ट हैं।"
            else:
                ack = "Understood. You focused on technical trade-offs and measurable outcomes."

        # Default conversational bridge
        else:
            if language == "te-IN":
                ack = "అర్థమైంది. మీరు చెప్పిన సమాచారం ఆధారంగా:"
            elif language == "hi-IN":
                ack = "समझ गया। आपके बताए गए विवरण के आधार पर:"
            else:
                ack = "Got it. Building on what you just shared:"

    next_text = ""
    if next_question_spec:
        next_text = next_question_spec.get(language) or next_question_spec.get("text", "")

    spoken_prompt = f"{ack} {next_text}".strip()
    return spoken_prompt, ack
