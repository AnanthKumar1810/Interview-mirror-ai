"""Authored fallback questions for the two additional frontend domains."""

EXTRA_TRACK_LABELS = {"backend": "Backend Engineering", "data": "Data Engineering"}

EXTRA_QUESTION_BANK = {
    "backend": [
        {
            "en-IN": "Explain how you would design a reliable REST API. How would you validate input, handle errors, and test it?",
            "te-IN": "నమ్మదగిన REST APIని ఎలా రూపొందిస్తారు? ఇన్‌పుట్‌ను ఎలా ధృవీకరిస్తారు, లోపాలను ఎలా నిర్వహిస్తారు, పరీక్షలు ఎలా చేస్తారు?",
            "hi-IN": "आप एक भरोसेमंद REST API कैसे बनाएँगे? इनपुट की जाँच, त्रुटियों का प्रबंधन और परीक्षण कैसे करेंगे?",
            "keywords": ["api", "rest", "validation", "error", "test", "status code"],
        },
        {
            "en-IN": "An API becomes slow under concurrent traffic. How would you measure the bottleneck and decide between caching, indexing, and asynchronous work?",
            "te-IN": "ఒక APIకి ఒకేసారి ఎక్కువ అభ్యర్థనలు వచ్చినప్పుడు అది నెమ్మదిస్తుంది. సమస్యను ఎలా కొలుస్తారు? క్యాషింగ్, ఇండెక్సింగ్, అసింక్ పనిలో దేనిని ఎంచుకుంటారు?",
            "hi-IN": "कई अनुरोध आने पर API धीमा हो जाता है। बाधा को कैसे मापेंगे और कैशिंग, इंडेक्सिंग या असिंक्रोनस काम में कैसे चुनेंगे?",
            "keywords": ["latency", "concurrency", "cache", "index", "async", "measure"],
        },
        {
            "en-IN": "Design a backend that survives retries and partial failures. How would you make writes idempotent and observe failures in production?",
            "te-IN": "రిట్రైలు, పాక్షిక వైఫల్యాలు ఉన్నా పనిచేసే బ్యాకెండ్‌ను రూపొందించండి. రైట్లను ఐడెంపోటెంట్‌గా ఎలా చేస్తారు? ప్రొడక్షన్‌లో వైఫల్యాలను ఎలా గమనిస్తారు?",
            "hi-IN": "रीट्राई और आंशिक विफलताओं में भी चलने वाला बैकएंड बनाइए। लिखने के काम को आइडेम्पोटेंट कैसे बनाएँगे और विफलताओं पर नज़र कैसे रखेंगे?",
            "keywords": ["retry", "idempotency", "transaction", "failure", "logging", "monitoring"],
        },
    ],
    "data": [
        {
            "en-IN": "Describe a data pipeline you built. What are its sources, transformations, outputs, and quality checks?",
            "te-IN": "మీరు నిర్మించిన డేటా పైప్‌లైన్‌ను వివరించండి. దాని మూలాలు, మార్పులు, అవుట్‌పుట్‌లు, నాణ్యత పరీక్షలు ఏమిటి?",
            "hi-IN": "आपने जो डेटा पाइपलाइन बनाई है, उसका वर्णन करें। उसके स्रोत, बदलाव, आउटपुट और गुणवत्ता जाँच क्या हैं?",
            "keywords": ["pipeline", "source", "transform", "output", "quality", "test"],
        },
        {
            "en-IN": "A daily data job has duplicate and late arriving records. How would you make ingestion idempotent and backfills safe?",
            "te-IN": "రోజువారీ డేటా జాబ్‌లో నకిలీ, ఆలస్యంగా వచ్చే రికార్డులు ఉన్నాయి. ఇంజెషన్‌ను ఐడెంపోటెంట్‌గా, బ్యాక్‌ఫిల్‌లను సురక్షితంగా ఎలా చేస్తారు?",
            "hi-IN": "एक दैनिक डेटा जॉब में डुप्लिकेट और देर से आने वाले रिकॉर्ड हैं। इनजेशन को आइडेम्पोटेंट और बैकफिल को सुरक्षित कैसे बनाएँगे?",
            "keywords": ["duplicate", "late", "idempotency", "backfill", "watermark", "deduplication"],
        },
        {
            "en-IN": "Design a streaming analytics pipeline. How would you handle schema changes, partitioning, and recovery after a consumer fails?",
            "te-IN": "స్ట్రీమింగ్ అనలిటిక్స్ పైప్‌లైన్‌ను రూపొందించండి. స్కీమా మార్పులు, పార్టిషనింగ్, కన్స్యూమర్ వైఫల్యం తర్వాత రికవరీని ఎలా నిర్వహిస్తారు?",
            "hi-IN": "स्ट्रीमिंग एनालिटिक्स पाइपलाइन डिज़ाइन करें। स्कीमा बदलाव, पार्टिशनिंग और कंज़्यूमर विफल होने पर रिकवरी कैसे सँभालेंगे?",
            "keywords": ["stream", "schema", "partition", "consumer", "checkpoint", "recovery"],
        },
    ],
}
