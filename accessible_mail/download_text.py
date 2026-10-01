"""User-facing download safety errors in the supported interface languages."""

_KEYS = (
    "حجم المرفق المستلم يتجاوز الحد المسموح وهو 5 غيغابايت.",
    "تعذر تنزيل المرفق كاملاً؛ بيانات المرفق غير صالحة أو غير مكتملة.",
    "تعذر حفظ المرفق. تحقق من المساحة المتاحة وصلاحية الكتابة ودعم القرص للملفات الكبيرة.",
    "نص الرسالة كبير جداً لعرضه بأمان؛ المرفقات لها حد تنزيل مستقل.",
    "لا يسمح بتنزيل الصور عبر نفق وكيل غير متحقق منه.",
    "تم منع الاتصال بعنوان صورة غير آمن.",
)

_TEXT = {
    "en": (
        "The received attachment exceeds the 5 GB download limit.",
        "The attachment could not be downloaded completely; its data is invalid or incomplete.",
        "Unable to save the attachment. Check free space, write permission and support for large files on the drive.",
        "The message text is too large to display safely. Attachments have a separate download limit.",
        "Image downloads through an unverified proxy tunnel are not allowed.",
        "A connection to an unsafe image address was blocked.",
    ),
    "fr": (
        "La pièce jointe reçue dépasse la limite de téléchargement de 5 Go.",
        "La pièce jointe n’a pas pu être téléchargée entièrement : ses données sont invalides ou incomplètes.",
        "Impossible d’enregistrer la pièce jointe. Vérifiez l’espace libre, les droits d’écriture et la prise en charge des fichiers volumineux par le disque.",
        "Le texte du message est trop volumineux pour être affiché en toute sécurité. Les pièces jointes ont une limite distincte.",
        "Le téléchargement d’images par un tunnel proxy non vérifié n’est pas autorisé.",
        "Une connexion vers une adresse d’image non sûre a été bloquée.",
    ),
    "de": (
        "Der empfangene Anhang überschreitet das Downloadlimit von 5 GB.",
        "Der Anhang konnte nicht vollständig heruntergeladen werden; seine Daten sind ungültig oder unvollständig.",
        "Der Anhang konnte nicht gespeichert werden. Prüfen Sie freien Speicherplatz, Schreibrechte und die Unterstützung großer Dateien auf dem Laufwerk.",
        "Der Nachrichtentext ist für eine sichere Anzeige zu groß. Anhänge haben ein eigenes Downloadlimit.",
        "Bilddownloads über einen ungeprüften Proxy-Tunnel sind nicht erlaubt.",
        "Eine Verbindung zu einer unsicheren Bildadresse wurde blockiert.",
    ),
    "es": (
        "El archivo adjunto recibido supera el límite de descarga de 5 GB.",
        "No se pudo descargar el adjunto por completo; sus datos son inválidos o están incompletos.",
        "No se pudo guardar el adjunto. Compruebe el espacio libre, los permisos de escritura y que la unidad admita archivos grandes.",
        "El texto del mensaje es demasiado grande para mostrarlo de forma segura. Los adjuntos tienen un límite de descarga independiente.",
        "No se permite descargar imágenes mediante un túnel proxy no verificado.",
        "Se bloqueó una conexión a una dirección de imagen no segura.",
    ),
    "tr": (
        "Alınan ek, 5 GB indirme sınırını aşıyor.",
        "Ek tamamen indirilemedi; verileri geçersiz veya eksik.",
        "Ek kaydedilemedi. Boş alanı, yazma izinlerini ve sürücünün büyük dosya desteğini kontrol edin.",
        "İleti metni güvenli görüntüleme için çok büyük. Eklerin ayrı bir indirme sınırı vardır.",
        "Doğrulanmamış bir proxy tüneli üzerinden resim indirilmesine izin verilmez.",
        "Güvenli olmayan bir resim adresine bağlantı engellendi.",
    ),
    "hi": (
        "प्राप्त अटैचमेंट 5 GB की डाउनलोड सीमा से बड़ा है।",
        "अटैचमेंट पूरा डाउनलोड नहीं हो सका; उसका डेटा अमान्य या अधूरा है।",
        "अटैचमेंट सहेजा नहीं जा सका। खाली जगह, लिखने की अनुमति और ड्राइव पर बड़ी फ़ाइलों के समर्थन की जाँच करें।",
        "संदेश का पाठ सुरक्षित रूप से दिखाने के लिए बहुत बड़ा है। अटैचमेंट की डाउनलोड सीमा अलग है।",
        "बिना सत्यापन वाले प्रॉक्सी टनल से चित्र डाउनलोड करने की अनुमति नहीं है।",
        "असुरक्षित चित्र पते से कनेक्शन रोक दिया गया।",
    ),
    "zh-CN": (
        "收到的附件超过了 5 GB 的下载上限。",
        "无法完整下载附件；其数据无效或不完整。",
        "无法保存附件。请检查可用空间、写入权限以及磁盘是否支持大文件。",
        "邮件正文过大，无法安全显示。附件有独立的下载上限。",
        "不允许通过未经验证的代理隧道下载图片。",
        "已阻止连接到不安全的图片地址。",
    ),
    "ru": (
        "Полученное вложение превышает предел загрузки в 5 ГБ.",
        "Не удалось полностью скачать вложение: его данные некорректны или неполны.",
        "Не удалось сохранить вложение. Проверьте свободное место, права записи и поддержку больших файлов на диске.",
        "Текст письма слишком велик для безопасного отображения. Для вложений установлен отдельный предел загрузки.",
        "Загрузка изображений через непроверенный прокси-туннель запрещена.",
        "Подключение к небезопасному адресу изображения заблокировано.",
    ),
    "ja": (
        "受信した添付ファイルがダウンロード上限の 5 GB を超えています。",
        "添付ファイルを完全にダウンロードできませんでした。データが無効か不完全です。",
        "添付ファイルを保存できません。空き容量、書き込み権限、ドライブが大容量ファイルに対応しているかを確認してください。",
        "メール本文が大きすぎるため、安全に表示できません。添付ファイルのダウンロード上限は別に設定されています。",
        "未検証のプロキシトンネル経由で画像をダウンロードすることはできません。",
        "安全でない画像アドレスへの接続をブロックしました。",
    ),
}

DOWNLOAD_TRANSLATIONS = {language: dict(zip(_KEYS, values, strict=True)) for language, values in _TEXT.items()}
