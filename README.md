# Power Accessible Mail

هذا هو المستودع الرسمي لتنزيل إصدارات وتحديثات Power Accessible Mail.

لا يحتوي هذا المستودع على شيفرة البرنامج. تحفظ ملفات التثبيت والنسخ المحمولة وملفات SHA-256 في صفحة الإصدارات فقط.

## الإصدار المستقر

الإصدار `1.2.15` إصدار مستقر غير موقع رقمياً ومتاح بمعماريتي 64 بت و32 بت. قد يعرض Windows تحذير «ناشر غير معروف» أثناء التثبيت.

## التنزيلات المتاحة

- [تنزيل مثبت 64 بت للإصدار 1.2.15](https://github.com/alikrstle/PowerAccessibleMail/releases/download/v1.2.15/PowerAccessibleMailSetup-1.2.15-win-x64-UNSIGNED.exe)
- [تنزيل مثبت 32 بت للإصدار 1.2.15](https://github.com/alikrstle/PowerAccessibleMail/releases/download/v1.2.15/PowerAccessibleMailSetup-1.2.15-win-x86-UNSIGNED.exe)

- الإصدار المستقر الحالي: `1.2.15`.
- `PowerAccessibleMailSetup-*-win-x64`: مثبت Windows إصدار 64 بت.
- `PowerAccessibleMailSetup-*-win-x86`: مثبت Windows إصدار 32 بت.
- الملفات التي ينتهي اسمها بـ `UNSIGNED` غير موقعة رقمياً. تحقق من بصمة SHA-256 المرفقة قبل التشغيل.

المطور: صولجان الشرق  
المالك: علي الأمير  
الاسم الإنجليزي: Soljan.AlSharq.

---

This is the official repository for Power Accessible Mail releases and updates.

The repository does not contain the application source code. Installers, portable packages, and SHA-256 manifests are available only from the Releases page.

## Stable release

Version `1.2.15` is an unsigned stable release, available for both x64 and x86 Windows. Windows may display an “Unknown publisher” warning during installation.

## Available downloads

- [Download the 1.2.15 64-bit installer](https://github.com/alikrstle/PowerAccessibleMail/releases/download/v1.2.15/PowerAccessibleMailSetup-1.2.15-win-x64-UNSIGNED.exe)
- [Download the 1.2.15 32-bit installer](https://github.com/alikrstle/PowerAccessibleMail/releases/download/v1.2.15/PowerAccessibleMailSetup-1.2.15-win-x86-UNSIGNED.exe)

- Current stable release: `1.2.15`.
- `PowerAccessibleMailSetup-*-win-x64`: 64-bit Windows installer.
- `PowerAccessibleMailSetup-*-win-x86`: 32-bit Windows installer.
- Files ending in `UNSIGNED` are not digitally signed. Verify them with the included SHA-256 manifest before running.

Developer: Soljan.AlSharq.  
Owner: Ali Al-Amir

## Official website / الموقع الرسمي

The source of the Soljan AlSharq website is maintained in [`website/`](website/).
It reads the pinned stable release from this repository and publishes the
verified x64 and x86 installer links. Website quality checks run automatically; production
deployment to the existing Cloudflare Pages project is a manual protected
workflow.

توجد ملفات موقع صولجان الشرق في المجلد [`website/`](website/). يقرأ الموقع
الإصدار المستقر المحدد في هذا المستودع ويعرض روابط نسختي 64 بت و32 بت بعد التحقق منها. تعمل
فحوص الجودة تلقائياً، أما النشر إلى مشروع Cloudflare Pages الإنتاجي فهو إجراء
يدوي محمي.
