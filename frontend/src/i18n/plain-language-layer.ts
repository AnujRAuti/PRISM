/**
 * Plain-Language Multi-Register Content Architecture Engine (Section 7 of Specification)
 * 
 * Maps canonical technical findings and project events into three distinct presentation registers:
 * 1. Reviewer Register: High precision, technical terminology, confidence metrics.
 * 2. Supervisor Register: Plain, direct, actionable field instructions ("do this, then this").
 * 3. Citizen Register: Non-alarmist, reassuring, plain civic status.
 */

export interface FindingTranslation {
  reviewer: string;
  supervisor: string;
  citizen: string;
}

export interface MultiRegisterRegistry {
  [canonicalKey: string]: Record<string, FindingTranslation>;
}

export const PLAIN_LANGUAGE_FINDINGS: MultiRegisterRegistry = {
  gps_deviation_exceeds_geofence: {
    en: {
      reviewer: 'GPS deviation of 340m exceeds the 150m geofence threshold (confidence 0.88).',
      supervisor: 'The location in this photo doesn’t match the project site — please retake it at the correct site location.',
      citizen: 'This project’s location details are currently being reviewed by the engineering team.',
    },
    hi: {
      reviewer: '340 मीटर का जीपीएस विचलन 150 मीटर की जियोफेंस सीमा से अधिक है (सटीकता 0.88)।',
      supervisor: 'इस फोटो का स्थान कार्य स्थल से मेल नहीं खा रहा है — कृपया सही स्थल पर जाकर दोबारा फोटो खींचें।',
      citizen: 'इस परियोजना के स्थान का विवरण वर्तमान में विभागीय टीम द्वारा जांचा जा रहा है।',
    },
    mr: {
      reviewer: '340 मीटरचे जीपीएस विचलन 150 मीटरच्या जिओफेन्स मर्यादेपेक्षा जास्त आहे.',
      supervisor: 'या फोटोचे स्थान कार्यस्थळाशी जुळत नाही — कृपया योग्य ठिकाणी जाऊन पुन्हा फोटो काढा.',
      citizen: 'या प्रकल्पाच्या स्थानाची माहिती सध्या तपासली जात आहे.',
    },
    bn: {
      reviewer: '৩৪০ মিটার জিপিএস বিচ্যুতি নির্ধারিত ১৫০ মিটার সীমার বাইরে (নির্ভুলতা ০.৮৮)।',
      supervisor: 'এই ছবির অবস্থান প্রকল্পের স্থানের সাথে মিলছে না — দয়া করে সঠিক স্থানে গিয়ে পুনরায় ছবি তুলুন।',
      citizen: 'এই প্রকল্পের অবস্থানের তথ্য বর্তমানে পর্যালোচনা করা হচ্ছে।',
    },
    ta: {
      reviewer: '340மீ ஜிபிஎஸ் விலகல் 150மீ புவிவேலி வரம்பை மீறுகிறது.',
      supervisor: 'இந்தப் புகைப்படத்தின் இருப்பிடம் திட்ட தளத்துடன் பொருந்தவில்லை — சரியான இடத்தில் மீண்டும் படம் எடுக்கவும்.',
      citizen: 'இந்தத் திட்டத்தின் இருப்பிட விவரங்கள் தற்போது மதிப்பாய்வு செய்யப்படுகின்றன.',
    },
    te: {
      reviewer: '340మీ జీపీఎస్ విచలనం 150మీ జియోఫెన్స్ పరిధిని మించిపోయింది.',
      supervisor: 'ఈ ఫోటో లొకేషన్ ప్రాజెక్ట్ స్థలంతో సరిపోలడం లేదు — దయచేసి సరైన ప్రదేశంలో మళ్లీ ఫోటో తీయండి.',
      citizen: 'ఈ ప్రాజెక్ట్ స్థాన వివరాలు ప్రస్తుతం పరిశీలనలో ఉన్నాయి.',
    },
    ur: {
      reviewer: '340 میٹر کا جی پی ایس انحراف 150 میٹر کی حد سے زیادہ ہے۔',
      supervisor: 'اس تصویر کا مقام کام کی جگہ سے میل نہیں کھاتا — براہ کرم صحیح جگہ پر دوبارہ تصویر لیں۔',
      citizen: 'اس منصوبے کے مقام کی تفصیلات کا جائزہ لیا جا رہا ہے۔',
    },
  },

  duplicate_evidence_found: {
    en: {
      reviewer: 'High perceptual similarity (94.7%) with evidence EVD-2025-1832 in distinct district.',
      supervisor: 'This photo looks identical to one uploaded previously — please take a fresh, live photo of the work done today.',
      citizen: 'Recent work photos are currently being verified by the department.',
    },
    hi: {
      reviewer: 'अन्य जिले के साक्ष्य EVD-2025-1832 के साथ 94.7% दृश्य समानता पाई गई।',
      supervisor: 'यह फोटो पुरानी फोटो जैसी दिख रही है — कृपया आज किए गए कार्य की ताज़ा लाइव फोटो खींचें।',
      citizen: 'हालिया कार्य की तस्वीरों का विभाग द्वारा सत्यापन किया जा रहा है।',
    },
    mr: {
      reviewer: 'दुसऱ्या जिल्ह्यातील साहित्याशी 94.7% दृश्य समानता आढळली.',
      supervisor: 'हा फोटो पूर्वीच्या फोटोसारखा दिसतो — कृपया आज केलेल्या कामाचा नवीन फोटो काढा.',
      citizen: 'नुकत्याच झालेल्या कामाच्या फोटोंची पडताळणी सुरू आहे.',
    },
    bn: {
      reviewer: 'অন্য জেলার নথির সাথে ৯৪.৭% দৃশ্যগত মিল পাওয়া গেছে।',
      supervisor: 'এই ছবিটি আগের একটি ছবির মতো দেখাচ্ছে — দয়া করে আজকের কাজের একটি নতুন ছবি তুলুন।',
      citizen: 'সাম্প্রতিক কাজের ছবিগুলি বিভাগ দ্বারা যাচাই করা হচ্ছে।',
    },
    ta: {
      reviewer: 'வேறு மாவட்டத்தின் ஆதாரத்துடன் 94.7% காட்சி ஒற்றுமை கண்டறியப்பட்டது.',
      supervisor: 'இந்தப் புகைப்படம் பழைய புகைப்படத்தைப் போன்றே உள்ளது — இன்று செய்த பணியின் புதிய படத்தை எடுக்கவும்.',
      citizen: 'சமீபத்திய பணிப் புகைப்படங்கள் துறையால் சரிபார்க்கப்படுகின்றன.',
    },
    te: {
      reviewer: 'మరొక జిల్లా సాక్ష్యంతో 94.7% సారూప్యత గుర్తించబడింది.',
      supervisor: 'ఈ ఫోటో పాత ఫోటోలా కనిపిస్తోంది — దయచేసి ఈరోజు చేసిన పనికి సంబంధించిన కొత్త ఫోటో తీయండి.',
      citizen: 'ఇటీవలి పని ఫోటోలు విభాగం ద్వారా ధృవీకరించబడుతున్నాయి.',
    },
    ur: {
      reviewer: 'دیگر ضلع کے ثبوت سے 94.7 فیصد مماثلت پائی گئی۔',
      supervisor: 'یہ تصویر پرانی تصویر جیسی لگتی ہے — براہ کرم آج کے کام کی تازہ تصویر لیں۔',
      citizen: 'حالیہ کام کی تصاویر کی تصدیق کی جا رہی ہے۔',
    },
  },

  claim_object_mismatch: {
    en: {
      reviewer: 'Vision model detected 0 target assets matching the claimed sanction of 10 solar street lights.',
      supervisor: 'The photo does not clearly show the completed street lights — please take a clear, wide shot showing the installed poles.',
      citizen: 'The latest progress report is being inspected on site.',
    },
    hi: {
      reviewer: 'दावे के अनुसार 10 सोलर लाइटों में से 0 इकाइयां पहचानी गईं (विसंगति)।',
      supervisor: 'फोटो में लगाई गई स्ट्रीट लाइटें साफ नहीं दिख रही हैं — कृपया खंभे और लाइट साफ दिखाते हुए फोटो खींचें।',
      citizen: 'नवीनतम प्रगति की विभागीय टीम द्वारा साइट पर जांच की जा रही है।',
    },
    mr: {
      reviewer: 'दाव्यानुसार 10 सोलर दिव्यांपैकी 0 युनिट्स आढळले.',
      supervisor: 'फोटोमध्ये बसवलेले दिवे स्पष्ट दिसत नाहीत — कृपया खांब आणि दिवे स्पष्ट दिसणारा फोटो काढा.',
      citizen: 'प्रगतीची प्रत्यक्ष तपासणी सुरू आहे.',
    },
    bn: {
      reviewer: 'দাবিকৃত ১০টি সোলার লাইটের মধ্যে ০টি শনাক্ত হয়েছে।',
      supervisor: 'ছবিতে লাগানো লাইটগুলো পরিষ্কার দেখা যাচ্ছে না — দয়া করে খুঁটি ও লাইট স্পষ্ট করে ছবি তুলুন।',
      citizen: 'সর্বশেষ অগ্রগতি বিভাগীয় দল দ্বারা খতিয়ে দেখা হচ্ছে।',
    },
    ta: {
      reviewer: 'கோரப்பட்ட 10 சோலார் விளக்குகளில் 0 கண்டறியப்பட்டது.',
      supervisor: 'புகைப்படத்தில் விளக்குகள் தெளிவாகத் தெரியவில்லை — தயவுசெய்து விளக்குகள் தெளிவாகத் தெரியும் வகையில் படம் எடுக்கவும்.',
      citizen: 'சமீபத்திய முன்னேற்றம் நேரில் ஆய்வு செய்யப்படுகிறது.',
    },
    te: {
      reviewer: 'క్లెయిమ్ చేసిన 10 సోలార్ లైట్లలో 0 యూనిట్లు గుర్తించబడ్డాయి.',
      supervisor: 'ఫోటోలో లైట్లు స్పష్టంగా కనిపించడం లేదు — దయచేసి లైట్లు స్పష్టంగా కనిపించేలా ఫోటో తీయండి.',
      citizen: 'తాజా పురోగతి పరిశీలించబడుతోంది.',
    },
    ur: {
      reviewer: 'دعوی کردہ 10 سولر لائٹس میں سے 0 شناخت ہوئیں۔',
      supervisor: 'تصویر میں لائٹس واضح نہیں ہیں — براہ کرم کھمبے اور لائٹس واضح دکھاتے ہوئے تصویر لیں۔',
      citizen: 'حالیہ کام کا موقع پر معائنہ کیا جا رہا ہے۔',
    },
  },

  incomplete_evidence_bundle: {
    en: {
      reviewer: 'Stage-2 subgrade milestone missing required cross-section photographs and tensile test PDF.',
      supervisor: 'Missing required document — please upload the Stage-2 Quality Inspection Certificate.',
      citizen: 'Work is underway according to schedule.',
    },
    hi: {
      reviewer: 'स्टेज-2 सबग्रेड मील के पत्थर की आवश्यक क्रॉस-सेक्शन फोटो और लैब टेस्ट अनुपलब्ध है।',
      supervisor: 'आवश्यक दस्तावेज बाकी है — कृपया स्टेज-2 गुणवत्ता निरीक्षण प्रमाण पत्र अपलोड करें।',
      citizen: 'कार्य समय सारिणी के अनुसार प्रगति पर है।',
    },
    mr: {
      reviewer: 'स्टेज-2 गुणवत्ता चाचणी प्रमाणपत्र गहाळ आहे.',
      supervisor: 'कृपया स्टेज-2 गुणवत्ता प्रमाणपत्र अपलोड करा.',
      citizen: 'काम वेळेनुसार सुरू आहे.',
    },
    bn: {
      reviewer: 'ধাপ-২ এর গুণমান পরীক্ষার সার্টিফিকেট অনুপস্থিত।',
      supervisor: 'প্রয়োজনীয় নথি বাকি — দয়া করে ধাপ-২ পরিদর্শন সার্টিফিকেট আপলোড করুন।',
      citizen: 'কাজ নির্ধারিত সময় অনুযায়ী চলছে।',
    },
    ta: {
      reviewer: 'படிநிலை-2 தரச் சான்றிதழ் விடுபட்டுள்ளது.',
      supervisor: 'தேவையான ஆவணம் விடுபட்டுள்ளது — தயவுசெய்து தரச் சான்றிதழைப் பதிவேற்றவும்.',
      citizen: 'பணிகள் திட்டமிட்டபடி நடைபெற்று வருகின்றன.',
    },
    te: {
      reviewer: 'స్టేజ్-2 నాణ్యత తనిఖీ పత్రం లేదు.',
      supervisor: 'దయచేసి స్టేజ్-2 క్వాలిటీ సర్టిఫికేట్ అప్‌లోడ్ చేయండి.',
      citizen: 'పనులు షెడ్యూల్ ప్రకారం జరుగుతున్నాయి.',
    },
    ur: {
      reviewer: 'مرحلہ 2 کا کوالٹی ٹیسٹ سرٹیفکیٹ موجود نہیں ہے۔',
      supervisor: 'براہ کرم مرحلہ 2 کا کوالٹی سرٹیفکیٹ اپ لوڈ کریں۔',
      citizen: 'کام شیڈول کے مطابق جاری ہے۔',
    },
  },
};

/**
 * Helper to resolve a finding string into the target user role's register
 */
export function resolveFindingText(
  canonicalKey: string,
  targetRole: 'CITIZEN' | 'SUPERVISOR' | 'REVIEWER' | string,
  lang = 'en'
): string {
  const findingGroup = PLAIN_LANGUAGE_FINDINGS[canonicalKey];
  if (!findingGroup) return canonicalKey;

  const langDict = findingGroup[lang] || findingGroup.en;
  if (!langDict) return canonicalKey;

  if (targetRole === 'CITIZEN') return langDict.citizen;
  if (targetRole === 'SUPERVISOR') return langDict.supervisor;
  return langDict.reviewer;
}

/**
 * Plain-language project status mapper
 */
export function getPlainProjectStatus(
  status: 'IN_PROGRESS' | 'COMPLETED' | 'UNDER_AUDIT' | 'FLAGGED_HOLD',
  role: 'CITIZEN' | 'SUPERVISOR' | 'REVIEWER'
): { label: string; color: string; desc: string } {
  if (role === 'CITIZEN') {
    switch (status) {
      case 'COMPLETED':
        return { label: 'Completed (कार्य पूर्ण)', color: 'bg-india-green/15 text-india-green border-india-green/30', desc: 'Work has been finished' };
      case 'IN_PROGRESS':
        return { label: 'In Progress (कार्य चालू)', color: 'bg-saffron/15 text-saffron-deep border-saffron/30', desc: 'Work is currently ongoing' };
      case 'UNDER_AUDIT':
      case 'FLAGGED_HOLD':
        return { label: 'Under Review (समीक्षा जारी)', color: 'bg-navy/15 text-navy dark:text-[#7FA8D9] border-navy/30', desc: 'Department is checking details' };
    }
  }

  if (role === 'SUPERVISOR') {
    switch (status) {
      case 'COMPLETED':
        return { label: 'Approved & Closed', color: 'bg-india-green/15 text-india-green', desc: 'All evidence accepted' };
      case 'IN_PROGRESS':
        return { label: 'Uploads Needed', color: 'bg-saffron/15 text-saffron-deep font-bold', desc: 'Capture next stage photo' };
      case 'UNDER_AUDIT':
      case 'FLAGGED_HOLD':
        return { label: 'Action Needed: Retake Photo', color: 'bg-risk-high/15 text-risk-high font-bold', desc: 'See reviewer note' };
    }
  }

  // Reviewer
  switch (status) {
    case 'COMPLETED':
      return { label: 'COMPLETED (Integrity Verified)', color: 'bg-india-green/15 text-india-green', desc: 'Milestones disbursed' };
    case 'IN_PROGRESS':
      return { label: 'IN_PROGRESS', color: 'bg-surface-sunken text-ink-secondary', desc: 'Awaiting milestones' };
    case 'UNDER_AUDIT':
      return { label: 'UNDER_AUDIT', color: 'bg-risk-medium/15 text-risk-medium', desc: 'Pending lead sign-off' };
    case 'FLAGGED_HOLD':
      return { label: 'FLAGGED_HOLD (Disbursement Stopped)', color: 'bg-risk-critical/15 text-risk-critical font-bold', desc: 'Critical anomaly triggered' };
  }
}

