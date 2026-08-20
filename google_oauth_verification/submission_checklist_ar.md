# قائمة تحقق قبل إرسال طلب Google OAuth

## المتطلبات العامة

- [x] لديك نطاق Domain تملكه: `soljan-alsharq.com`.
- [x] تم التحقق من النطاق في Google Search Console بالحساب الأساسي مالك المشروع.
- [x] توجد صفحة رئيسية عامة للتطبيق على النطاق نفسه.
- [x] توجد سياسة خصوصية عامة بالعربية والإنجليزية على النطاق نفسه.
- [x] صفحة البرنامج تذكر اسم Power Accessible Mail ووظيفته بوضوح.
- [x] سياسة الخصوصية تشرح الوصول إلى Gmail والتخزين المحلي والتشفير والحذف.
- [x] بريد الدعم مضبوط في معلومات التطبيق والموقع.

## داخل Google Cloud Console

- [x] اسم التطبيق: Power Accessible Mail.
- [x] نوع المستخدم: External.
- [x] App domain / Homepage مضبوط على `https://soljan-alsharq.com/`.
- [x] Privacy policy URL مضبوط على `https://soljan-alsharq.com/privacy`.
- [x] Terms of service مضبوط على `https://soljan-alsharq.com/terms`.
- [x] Developer contact email مضبوط.
- [x] Authorized domains تحتوي على `soljan-alsharq.com`.
- [x] OAuth Client الحالي من نوع Desktop باسم Power Accessible Mail - Gmail API Limited.
- [x] Redirect URI المحلي يعمل مع البرنامج ويستخدم PKCE وstate وnonce.
- [x] النطاقات المعلنة تطابق ما يطلبه البرنامج.
- [ ] نقل حالة التطبيق من Testing إلى Production.
- [ ] فتح Prepare for Verification بعد النشر.

## النطاقات الحالية

- [x] `openid`
- [x] `email`
- [x] `profile`
- [x] `https://www.googleapis.com/auth/gmail.modify`

## فيديو العرض

- [ ] يوضح تسجيل الدخول من داخل البرنامج.
- [ ] يوضح شاشة موافقة Google كاملة.
- [ ] يوضح قراءة الرسائل.
- [ ] يوضح الروابط والمرفقات.
- [ ] يوضح إرسال رسالة أو الرد.
- [ ] يوضح تغيير حالة القراءة والنجمة والنقل إلى سلة Gmail.
- [ ] يوضح تنبيه خصوصية الترجمة واختيار الإلغاء أو المتابعة دون عرض رسالة شخصية.
- [ ] يوضح دليل البرنامج/الخصوصية داخل الواجهة.
- [ ] لا يحتوي على بيانات شخصية حقيقية.
- [ ] لغة شاشة موافقة Google مضبوطة على English.

## بعد الإرسال

- [ ] راقب بريد مالك المشروع ومحرريه.
- [ ] كن مستعدا لشرح استخدام `gmail.modify` للقراءة والإرسال وإدارة حالة الرسائل وسلة المحذوفات.
- [ ] كن مستعدا لاحتمال طلب تقييم أمني بسبب نطاق Gmail المقيد.
