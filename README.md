# Power Accessible Mail

هذا هو المستودع الرسمي لتنزيل إصدارات وتحديثات Power Accessible Mail.

لا يحتوي هذا المستودع على شيفرة البرنامج. تحفظ ملفات التثبيت والنسخ المحمولة وملفات SHA-256 في صفحة الإصدارات فقط.

## تنبيه صيانة نسخة 32 بت

نسخة Windows ذات معمارية 32 بت متوقفة مؤقتاً للصيانة والتحقق وإعادة الاختبار. أُزيلت ملفات `win-x86` من الإصدار الحالي، ويرجى عدم استخدام أي نسخة 32 بت محفوظة سابقاً إلى أن ننشر حزمة بديلة بعد اكتمال أعمال الصيانة.

## التنزيل المتاح

[تنزيل مثبت 64 بت للإصدار 1.2.13](https://github.com/alikrstle/PowerAccessibleMail/releases/download/v1.2.13/PowerAccessibleMailSetup-1.2.13-win-x64-UNSIGNED.exe)

- الإصدار الحالي: `1.2.13`.
- `PowerAccessibleMailSetup-*-win-x64`: مثبت Windows إصدار 64 بت.
- `win-x86`: غير متاح حالياً.
- الملفات التي ينتهي اسمها بـ `UNSIGNED` غير موقعة رقمياً. تحقق من بصمة SHA-256 المرفقة قبل التشغيل.

المطور: صولجان الشرق  
المالك: علي الأمير  
الاسم الإنجليزي: Soljan.AlSharq.

---

This is the official repository for Power Accessible Mail releases and updates.

The repository does not contain the application source code. Installers, portable packages, and SHA-256 manifests are available only from the Releases page.

## 32-bit edition maintenance notice

The 32-bit Windows edition is temporarily unavailable while it undergoes maintenance, verification, and retesting. The `win-x86` assets have been removed from the current release. Do not use previously saved 32-bit packages until a verified replacement is published.

## Available download

[Download the 1.2.13 64-bit installer](https://github.com/alikrstle/PowerAccessibleMail/releases/download/v1.2.13/PowerAccessibleMailSetup-1.2.13-win-x64-UNSIGNED.exe)

- Current release: `1.2.13`.
- `PowerAccessibleMailSetup-*-win-x64`: 64-bit Windows installer.
- `win-x86`: currently unavailable.
- Files ending in `UNSIGNED` are not digitally signed. Verify them with the included SHA-256 manifest before running.

Developer: Soljan.AlSharq.  
Owner: Ali Al-Amir

## Official website / الموقع الرسمي

The source of the Soljan AlSharq website is maintained in [`website/`](website/).
It reads the latest release from this repository and publishes the verified
x64 installer link. Website quality checks run automatically; production
deployment to the existing Cloudflare Pages project is a manual protected
workflow.

توجد ملفات موقع صولجان الشرق في المجلد [`website/`](website/). يقرأ الموقع
أحدث إصدار منشور في هذا المستودع ويعرض رابط نسخة 64 بت المتحقق منها. تعمل
فحوص الجودة تلقائياً، أما النشر إلى مشروع Cloudflare Pages الإنتاجي فهو إجراء
يدوي محمي.
