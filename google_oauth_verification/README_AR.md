# تجهيز موافقة Google OAuth

تساعد هذه الملفات في إرسال Power Accessible Mail إلى Google للمراجعة حتى يظهر تسجيل الدخول عبر المتصفح رسميا للمستخدمين.

## النطاق المستخدم

كل إصدارات البرنامج الجديدة تستخدم Gmail API بالنطاق:

`https://www.googleapis.com/auth/gmail.modify`

لا تطلب الإصدارات الجديدة نطاق `https://mail.google.com/`. تستخدم حسابات Gmail واجهة Gmail API للقراءة والإرسال وإدارة التصنيفات ونقل الرسائل إلى سلة المحذوفات.

## المتطلبات

- مشروع Google Cloud خاص بالتطبيق.
- تفعيل Gmail API.
- شاشة OAuth Consent Screen مكتملة.
- صفحة رئيسية للتطبيق على نطاق تملكه.
- سياسة خصوصية منشورة على النطاق نفسه.
- بريد دعم رسمي.
- شرح سبب طلب `gmail.modify`.
- فيديو يوضح تسجيل الدخول واستخدام وظائف Gmail.

## الاختبار قبل النشر

1. اجعل حالة التطبيق Testing.
2. أضف عناوين المختبرين ضمن Audience ثم Test users.
3. أنشئ OAuth Client من نوع Desktop app.
4. ضع بياناته في `google_gmail_api` داخل ملف `oauth_clients.json` الموحد.
5. أعط المختبرين البناء المطابق لأجهزتهم؛ نسختا x64 وx86 تستخدمان العميل نفسه والنطاق نفسه.

## النشر العام

1. افتح مشروع التطبيق وفعّل Gmail API.
2. أكمل اسم التطبيق وبريد الدعم وروابط الصفحة الرئيسية وسياسة الخصوصية.
3. تحقق من النطاق في Google Search Console وأضفه إلى Authorized domains.
4. أضف النطاقات `openid` و`email` و`profile` و`gmail.modify`.
5. انشر التطبيق إلى Production واختر Prepare for verification.
6. أرفق التبرير من `scope_justification_en.md`.
7. أرفق فيديو العرض المعد وفق `demo_video_script_ar.md`.
8. راقب بريد مالك المشروع للرد على طلبات Google.

## الملفات

- `privacy_policy_en.md`: سياسة الخصوصية الإنجليزية للنشر.
- `privacy_policy_ar.md`: النسخة العربية.
- `scope_justification_en.md`: تبرير النطاقات.
- `demo_video_script_ar.md`: سيناريو فيديو المراجعة.
- `homepage_content_ar.md`: نص صفحة البرنامج.
- `submission_checklist_ar.md`: قائمة التحقق.
