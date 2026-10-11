from __future__ import annotations


LANGUAGES = {
    "English": "en",
    "Urdu": "ur",
    "Arabic": "ar",
    "Spanish": "es",
    "Hindi": "hi",
    "Bangla": "bn",
}


TRANSLATIONS = {
    "Settings": {
        "es": "Configuración", "ur": "ترتیبات", "ar": "الإعدادات",
        "hi": "सेटिंग्स", "bn": "সেটিংস",
    },
    "Statistics": {
        "es": "Estadísticas", "ur": "اعداد و شمار", "ar": "الإحصاءات",
        "hi": "आँकड़े", "bn": "পরিসংখ্যান",
    },
    "Media inspector": {
        "es": "Inspector multimedia", "ur": "میڈیا انسپکٹر",
        "ar": "عارض الوسائط", "hi": "मीडिया निरीक्षक", "bn": "মিডিয়া পরিদর্শক",
    },
    "Media preview": {
        "es": "Vista previa", "ur": "میڈیا پیش نظارہ",
        "ar": "معاينة الوسائط", "hi": "मीडिया पूर्वावलोकन",
        "bn": "মিডিয়া প্রিভিউ",
    },
    "File attributes": {
        "es": "Atributos del archivo", "ur": "فائل کی خصوصیات",
        "ar": "خصائص الملف", "hi": "फ़ाइल विशेषताएँ", "bn": "ফাইল বৈশিষ্ট্য",
    },
    "Browse local media": {
        "es": "Buscar medios locales", "ur": "مقامی میڈیا منتخب کریں",
        "ar": "استعراض الوسائط المحلية", "hi": "स्थानीय मीडिया चुनें",
        "bn": "স্থানীয় মিডিয়া ব্রাউज़ করুন",
    },
    "Choose an existing audio or video file": {
        "es": "Elige un archivo de audio o vídeo existente",
        "ur": "موجودہ آڈیو یا ویڈیو فائل منتخب کریں",
        "ar": "اختر ملف صوت أو فيديو موجودًا",
        "hi": "मौजूदा ऑडियो या वीडियो फ़ाइल चुनें",
        "bn": "বিদ্যমান অডিও বা ভিডিও ফাইল নির্বাচন করুন",
    },
    "Audio and video files": {
        "es": "Archivos de audio y vídeo", "ur": "آڈیو اور ویڈیو فائلیں",
        "ar": "ملفات الصوت والفيديو", "hi": "ऑडियो और वीडियो फ़ाइलें",
        "bn": "অডিও ও ভিডিও ফাইল",
    },
    "All files": {
        "es": "Todos los archivos", "ur": "تمام فائلیں", "ar": "كل الملفات",
        "hi": "सभी फ़ाइलें", "bn": "সব ফাইল",
    },
    "Choose an existing supported audio or video file.": {
        "es": "Elige un archivo de audio o vídeo compatible existente.",
        "ur": "موجودہ معاون آڈیو یا ویڈیو فائل منتخب کریں۔",
        "ar": "اختر ملف صوت أو فيديو مدعومًا وموجودًا.",
        "hi": "मौजूदा समर्थित ऑडियो या वीडियो फ़ाइल चुनें।",
        "bn": "একটি বিদ্যমান সমর্থিত অডিও বা ভিডিও ফাইল নির্বাচন করুন।",
    },
    "Existing local file": {
        "es": "Archivo local existente", "ur": "موجودہ مقامی فائل",
        "ar": "ملف محلي موجود", "hi": "मौजूदा स्थानीय फ़ाइल",
        "bn": "বিদ্যমান স্থানীয় ফাইল",
    },
    "Local file": {
        "es": "Archivo local", "ur": "مقامی فائل",
        "ar": "ملف محلي", "hi": "स्थानीय फ़ाइल", "bn": "স্থানীয় ফাইল",
    },
    "No item selected": {
        "es": "Ningún elemento seleccionado", "ur": "کوئی آئٹم منتخب نہیں",
        "ar": "لم يتم تحديد عنصر", "hi": "कोई आइटम चयनित नहीं",
        "bn": "কোনো আইটেম নির্বাচন করা হয়নি",
    },
    "Select a file to preview": {
        "es": "Selecciona un archivo para obtener una vista previa",
        "ur": "پیش نظارہ کے لیے فائل منتخب کریں",
        "ar": "حدد ملفًا لمعاينته", "hi": "पूर्वावलोकन के लिए फ़ाइल चुनें",
        "bn": "প্রিভিউ দেখতে একটি ফাইল নির্বাচন করুন",
    },
    "Choose an existing file or select a downloaded task.": {
        "es": "Elige un archivo existente o selecciona una tarea descargada.",
        "ur": "موجودہ فائل منتخب کریں یا ڈاؤن لوڈ کردہ کام چنیں۔",
        "ar": "اختر ملفًا موجودًا أو مهمة تم تنزيلها.",
        "hi": "मौजूदा फ़ाइल चुनें या डाउनलोड किया गया कार्य चुनें।",
        "bn": "বিদ্যমান ফাইল বা ডাউনলোড করা কাজ নির্বাচন করুন।",
    },
    "Play audio/video": {
        "es": "Reproducir audio/vídeo", "ur": "آڈیو/ویڈیو چلائیں",
        "ar": "تشغيل الصوت/الفيديو", "hi": "ऑडियो/वीडियो चलाएँ",
        "bn": "অডিও/ভিডিও চালান",
    },
    "Play in app": {
        "es": "Reproducir en la aplicación", "ur": "ایپ میں چلائیں",
        "ar": "تشغيل داخل التطبيق", "hi": "ऐप में चलाएँ",
        "bn": "অ্যাপে চালান",
    },
    "Open in system player": {
        "es": "Abrir en el reproductor del sistema",
        "ur": "سسٹم پلیئر میں کھولیں",
        "ar": "فتح في مشغل النظام", "hi": "सिस्टम प्लेयर में खोलें",
        "bn": "সিস্টেম প্লেয়ারে খুলুন",
    },
    "Media player": {
        "es": "Reproductor multimedia", "ur": "میڈیا پلیئر",
        "ar": "مشغل الوسائط", "hi": "मीडिया प्लेयर", "bn": "মিডিয়া প্লেয়ার",
    },
    "Full screen": {
        "es": "Pantalla completa", "ur": "مکمل اسکرین",
        "ar": "ملء الشاشة", "hi": "पूर्ण स्क्रीन", "bn": "পূর্ণ পর্দা",
    },
    "Exit full screen": {
        "es": "Salir de pantalla completa", "ur": "مکمل اسکرین سے باہر",
        "ar": "الخروج من ملء الشاشة", "hi": "पूर्ण स्क्रीन से बाहर निकलें",
        "bn": "পূর্ণ পর্দা থেকে বের হন",
    },
    "Audio track": {
        "es": "Pista de audio", "ur": "آڈیو ٹریک",
        "ar": "المسار الصوتي", "hi": "ऑडियो ट्रैक", "bn": "অডিও ট্র্যাক",
    },
    "No audio tracks available": {
        "es": "No hay pistas de audio disponibles",
        "ur": "کوئی آڈیو ٹریک دستیاب نہیں",
        "ar": "لا توجد مسارات صوتية متاحة",
        "hi": "कोई ऑडियो ट्रैक उपलब्ध नहीं",
        "bn": "কোনো অডিও ট্র্যাক উপলভ্য নেই",
    },
    "Audio track unavailable": {
        "es": "Pista de audio no disponible", "ur": "آڈیو ٹریک دستیاب نہیں",
        "ar": "المسار الصوتي غير متاح", "hi": "ऑडियो ट्रैक उपलब्ध नहीं",
        "bn": "অডিও ট্র্যাক উপলভ্য নয়",
    },
    "VLC could not select this audio track.": {
        "es": "VLC no pudo seleccionar esta pista de audio.",
        "ur": "VLC یہ آڈیو ٹریک منتخب نہیں کر سکا۔",
        "ar": "تعذر على VLC تحديد هذا المسار الصوتي.",
        "hi": "VLC इस ऑडियो ट्रैक को चुन नहीं सका।",
        "bn": "VLC এই অডিও ট্র্যাক নির্বাচন করতে পারেনি।",
    },
    "Media player help": {
        "es": "Ayuda del reproductor multimedia", "ur": "میڈیا پلیئر کی مدد",
        "ar": "مساعدة مشغل الوسائط", "hi": "मीडिया प्लेयर सहायता",
        "bn": "মিডিয়া প্লেয়ার সহায়তা",
    },
    "Resize the player using its window edges, or choose Full screen or press F11. Press Escape to leave full screen. Use the volume slider to change sound; the percentage is shown beside it. Choose an audio track from the track list when the media provides multiple tracks. Video scales to the available player area.": {
        "ur": (
            "پلیئر کا سائز بدلنے کے لیے ونڈو کے کنارے کھینچیں، یا مکمل اسکرین "
            "منتخب کریں یا F11 دبائیں۔ مکمل اسکرین سے نکلنے کے لیے Escape دبائیں۔ "
            "آواز بدلنے کے لیے والیوم سلائیڈر استعمال کریں؛ اس کے ساتھ فیصد دکھائی "
            "جاتی ہے۔ اگر میڈیا میں متعدد ٹریک ہوں تو فہرست سے آڈیو ٹریک منتخب کریں۔ "
            "ویڈیو دستیاب پلیئر حصے کے مطابق ہو جائے گی۔"
        ),
    },
    "Pause": {
        "es": "Pausar", "ur": "روکیں", "ar": "إيقاف مؤقت",
        "hi": "रोकें", "bn": "বিরতি",
    },
    "Play": {
        "es": "Reproducir", "ur": "چلائیں", "ar": "تشغيل",
        "hi": "चलाएँ", "bn": "চালান",
    },
    "Stop": {
        "es": "Detener", "ur": "بند کریں", "ar": "إيقاف",
        "hi": "रोकें", "bn": "থামান",
    },
    "Volume": {
        "es": "Volumen", "ur": "آواز", "ar": "مستوى الصوت",
        "hi": "आवाज़", "bn": "ভলিউম",
    },
    "In-app playback unavailable": {
        "es": "Reproducción en la aplicación no disponible",
        "ur": "ایپ میں پلے بیک دستیاب نہیں",
        "ar": "التشغيل داخل التطبيق غير متاح",
        "hi": "ऐप में प्लेबैक उपलब्ध नहीं", "bn": "অ্যাপে প্লেব্যাক উপলভ্য নয়",
    },
    "VLC is required for in-app playback. Open this file in your system player instead?": {
        "es": "Se necesita VLC para reproducir en la aplicación. ¿Abrir este archivo en el reproductor del sistema?",
        "ur": "ایپ میں چلانے کے لیے VLC درکار ہے۔ کیا اس فائل کو سسٹم پلیئر میں کھولیں؟",
        "ar": "يلزم VLC للتشغيل داخل التطبيق. هل تريد فتح الملف في مشغل النظام؟",
        "hi": "ऐप में चलाने के लिए VLC आवश्यक है। क्या इस फ़ाइल को सिस्टम प्लेयर में खोलें?",
        "bn": "অ্যাপে চালাতে VLC প্রয়োজন। ফাইলটি কি সিস্টেম প্লেয়ারে খুলবেন?",
    },
    "VLC could not start playback.": {
        "es": "VLC no pudo iniciar la reproducción.",
        "ur": "VLC پلے بیک شروع نہیں کر سکا۔",
        "ar": "تعذر على VLC بدء التشغيل.",
        "hi": "VLC प्लेबैक शुरू नहीं कर सका।",
        "bn": "VLC প্লেব্যাক শুরু করতে পারেনি।",
    },
    "VLC could not play this media file.": {
        "es": "VLC no pudo reproducir este archivo multimedia.",
        "ur": "VLC یہ میڈیا فائل نہیں چلا سکا۔",
        "ar": "تعذر على VLC تشغيل ملف الوسائط هذا.",
        "hi": "VLC इस मीडिया फ़ाइल को नहीं चला सका।",
        "bn": "VLC এই মিডিয়া ফাইলটি চালাতে পারেনি।",
    },
    "Show file": {
        "es": "Mostrar archivo", "ur": "فائل دکھائیں", "ar": "إظهار الملف",
        "hi": "फ़ाइल दिखाएँ", "bn": "ফাইল দেখান",
    },
    "Copy link": {
        "es": "Copiar enlace", "ur": "لنک کاپی کریں", "ar": "نسخ الرابط",
        "hi": "लिंक कॉपी करें", "bn": "লিংক কপি করুন",
    },
    "Select a task to inspect": {
        "es": "Selecciona una tarea para inspeccionar",
        "ur": "جائزے کے لیے ایک کام منتخب کریں",
        "ar": "حدد مهمة لفحصها", "hi": "जाँचने के लिए कार्य चुनें",
        "bn": "পরীক্ষার জন্য একটি কাজ নির্বাচন করুন",
    },
    "Playback opens your system media player.": {
        "es": "La reproducción abre el reproductor multimedia del sistema.",
        "ur": "پلے بیک آپ کے سسٹم میڈیا پلیئر میں کھلے گا۔",
        "ar": "يفتح التشغيل مشغل الوسائط في النظام.",
        "hi": "प्लेबैक आपके सिस्टम मीडिया प्लेयर में खुलेगा।",
        "bn": "প্লেব্যাক আপনার সিস্টেম মিডিয়া প্লেয়ার খুলবে।",
    },
    "No task selected": {
        "es": "No hay ninguna tarea seleccionada", "ur": "کوئی کام منتخب نہیں",
        "ar": "لم يتم تحديد مهمة", "hi": "कोई कार्य चयनित नहीं",
        "bn": "কোনো কাজ নির্বাচিত হয়নি",
    },
    "Select a task before copying its link.": {
        "es": "Selecciona una tarea antes de copiar el enlace.",
        "ur": "لنک کاپی کرنے سے پہلے کام منتخب کریں۔",
        "ar": "حدد مهمة قبل نسخ رابطها.",
        "hi": "लिंक कॉपी करने से पहले कोई कार्य चुनें।",
        "bn": "লিংক কপি করার আগে একটি কাজ নির্বাচন করুন।",
    },
    "Link copied to clipboard.": {
        "es": "Enlace copiado al portapapeles.",
        "ur": "لنک کلپ بورڈ پر کاپی ہوگیا۔",
        "ar": "تم نسخ الرابط إلى الحافظة.",
        "hi": "लिंक क्लिपबोर्ड पर कॉपी किया गया।",
        "bn": "লিংক ক্লিপবোর্ডে কপি হয়েছে।",
    },
    "General": {
        "es": "General", "ur": "عام", "ar": "عام", "hi": "सामान्य", "bn": "সাধারণ",
    },
    "Speed & checks": {
        "es": "Velocidad y verificación", "ur": "رفتار اور جانچ",
        "ar": "السرعة والتحقق", "hi": "गति और जाँच", "bn": "গতি ও যাচাই",
    },
    "Connection": {
        "es": "Conexión", "ur": "کنکشن", "ar": "الاتصال",
        "hi": "कनेक्शन", "bn": "সংযোগ",
    },
    "Schedule & files": {
        "es": "Programación y archivos", "ur": "شیڈول اور فائلیں",
        "ar": "الجدولة والملفات", "hi": "शेड्यूल और फ़ाइलें", "bn": "সময়সূচি ও ফাইল",
    },
    "All tasks": {
        "es": "Todas las tareas", "ur": "تمام کام", "ar": "كل المهام",
        "hi": "सभी कार्य", "bn": "সব কাজ",
    },
    "Downloading": {
        "es": "Descargando", "ur": "ڈاؤن لوڈ ہو رہا ہے", "ar": "جارٍ التنزيل",
        "hi": "डाउनलोड हो रहा है", "bn": "ডাউনলোড হচ্ছে",
    },
    "Completed": {
        "es": "Completado", "ur": "مکمل", "ar": "مكتمل",
        "hi": "पूर्ण", "bn": "সম্পন্ন",
    },
    "Media library": {
        "es": "Biblioteca multimedia", "ur": "میڈیا لائبریری",
        "ar": "مكتبة الوسائط", "hi": "मीडिया लाइब्रेरी", "bn": "মিডিয়া লাইব্রেরি",
    },
    "Tools & utilities": {
        "es": "Herramientas y utilidades", "ur": "ٹولز اور سہولیات",
        "ar": "الأدوات والمرافق", "hi": "टूल और सुविधाएँ", "bn": "টুল ও উপযোগিতা",
    },
    "Image tools": {
        "es": "Herramientas de imagen", "ur": "تصویری ٹولز",
        "ar": "أدوات الصور", "hi": "छवि टूल", "bn": "ছবির টুল",
    },
    "Image gallery": {
        "es": "Galería de imágenes", "ur": "تصویری گیلری",
        "ar": "معرض الصور", "hi": "छवि गैलरी", "bn": "ছবির গ্যালারি",
    },
    "Dark mode": {
        "es": "Modo oscuro", "ur": "ڈارک موڈ", "ar": "الوضع الداكن",
        "hi": "डार्क मोड", "bn": "ডার্ক মোড",
    },
    "Language": {
        "es": "Idioma", "ur": "زبان", "ar": "اللغة",
        "hi": "भाषा", "bn": "ভাষা",
    },
    "Accessibility": {
        "es": "Accesibilidad", "ur": "رسائی", "ar": "إمكانية الوصول",
        "hi": "सुलभता", "bn": "অ্যাক্সেসিবিলিটি",
    },
    "Use larger text": {
        "es": "Usar texto más grande", "ur": "بڑا متن استعمال کریں",
        "ar": "استخدام نص أكبر", "hi": "बड़ा टेक्स्ट उपयोग करें",
        "bn": "বড় লেখা ব্যবহার করুন",
    },
    "High contrast": {
        "es": "Alto contraste", "ur": "زیادہ کنٹراسٹ", "ar": "تباين عالٍ",
        "hi": "उच्च कंट्रास्ट", "bn": "উচ্চ কনট্রাস্ট",
    },
    "Check for updates at startup": {
        "es": "Buscar actualizaciones al iniciar",
        "ur": "شروع پر اپ ڈیٹس دیکھیں",
        "ar": "التحقق من التحديثات عند بدء التشغيل",
        "hi": "शुरुआत में अपडेट जाँचें", "bn": "শুরুতে আপডেট দেখুন",
    },
    "Share diagnostic events": {
        "es": "Compartir eventos de diagnóstico",
        "ur": "تشخیصی واقعات شیئر کریں",
        "ar": "مشاركة أحداث التشخيص",
        "hi": "निदान इवेंट साझा करें", "bn": "ডায়াগনস্টিক ইভেন্ট শেয়ার করুন",
    },
    "Record local diagnostic events": {
        "es": "Registrar eventos de diagnóstico localmente",
        "ur": "تشخیصی واقعات مقامی طور پر ریکارڈ کریں",
        "ar": "تسجيل أحداث التشخيص محليًا",
        "hi": "निदान इवेंट स्थानीय रूप से रिकॉर्ड करें",
        "bn": "ডায়াগনস্টিক ইভেন্ট স্থানীয়ভাবে রেকর্ড করুন",
    },
    "Export local diagnostics…": {
        "es": "Exportar diagnósticos locales…",
        "ur": "مقامی تشخیص برآمد کریں…",
        "ar": "تصدير التشخيصات المحلية…",
        "hi": "स्थानीय निदान निर्यात करें…", "bn": "স্থানীয় ডায়াগনস্টিক রপ্তানি…",
    },
    "Check for updates now": {
        "es": "Buscar actualizaciones ahora",
        "ur": "ابھی اپ ڈیٹس دیکھیں",
        "ar": "التحقق من التحديثات الآن",
        "hi": "अभी अपडेट जाँचें", "bn": "এখনই আপডেট দেখুন",
    },
    "Save": {
        "es": "Guardar", "ur": "محفوظ کریں", "ar": "حفظ",
        "hi": "सहेजें", "bn": "সংরক্ষণ",
    },
    "Close": {
        "es": "Cerrar", "ur": "بند کریں", "ar": "إغلاق",
        "hi": "बंद करें", "bn": "বন্ধ করুন",
    },
    "Add download": {
        "es": "Añadir descarga", "ur": "ڈاؤن لوڈ شامل کریں",
        "ar": "إضافة تنزيل", "hi": "डाउनलोड जोड़ें", "bn": "ডাউনলোড যোগ করুন",
    },
    "Browse": {
        "es": "Examinar", "ur": "منتخب کریں", "ar": "استعراض",
        "hi": "ब्राउज़ करें", "bn": "ব্রাউজ",
    },
    "Paste a link, choose where to save it, and add it to your queue.": {
        "es": "Pega un enlace, elige dónde guardarlo y añádelo a la cola.",
        "ur": "لنک پیسٹ کریں، محفوظ کرنے کی جگہ چنیں اور قطار میں شامل کریں۔",
        "ar": "الصق رابطًا، واختر مكان الحفظ، ثم أضفه إلى قائمة التنزيل.",
        "hi": "लिंक पेस्ट करें, सेव स्थान चुनें और कतार में जोड़ें।",
        "bn": "লিংক পেস্ট করুন, সংরক্ষণের স্থান বেছে নিয়ে কিউতে যোগ করুন।",
    },
    "Use recommended": {
        "es": "Usar recomendado", "ur": "تجویز کردہ استعمال کریں",
        "ar": "استخدام الموصى به", "hi": "अनुशंसित उपयोग करें",
        "bn": "প্রস্তাবিত ব্যবহার করুন",
    },
    "Auto-fill copied links": {
        "es": "Rellenar enlaces copiados",
        "ur": "کاپی کیے گئے لنکس خود بھریں",
        "ar": "ملء الروابط المنسوخة تلقائيًا",
        "hi": "कॉपी किए लिंक अपने-आप भरें",
        "bn": "কপি করা লিংক স্বয়ংক্রিয়ভাবে পূরণ",
    },
    "Link": {
        "es": "Enlace", "ur": "لنک", "ar": "الرابط", "hi": "लिंक", "bn": "লিংক",
    },
    "Convert to MP3": {
        "es": "Convertir a MP3", "ur": "MP3 میں تبدیل کریں",
        "ar": "تحويل إلى MP3", "hi": "MP3 में बदलें", "bn": "MP3-তে রূপান্তর",
    },
    "Batch": {
        "es": "Lote", "ur": "بیچ", "ar": "دفعة", "hi": "बैच", "bn": "ব্যাচ",
    },
    "Sequence": {
        "es": "Secuencia", "ur": "سلسلہ", "ar": "تسلسل",
        "hi": "अनुक्रम", "bn": "ক্রম",
    },
    "More settings": {
        "es": "Más ajustes", "ur": "مزید ترتیبات", "ar": "مزيد من الإعدادات",
        "hi": "और सेटिंग्स", "bn": "আরও সেটিংস",
    },
    "Overall progress": {
        "es": "Progreso general", "ur": "مجموعی پیش رفت", "ar": "التقدم الإجمالي",
        "hi": "कुल प्रगति", "bn": "সামগ্রিক অগ্রগতি",
    },
    "Status": {
        "es": "Estado", "ur": "حیثیت", "ar": "الحالة", "hi": "स्थिति", "bn": "অবস্থা",
    },
    "Progress": {
        "es": "Progreso", "ur": "پیش رفت", "ar": "التقدم", "hi": "प्रगति", "bn": "অগ্রগতি",
    },
    "Transfer details": {
        "es": "Detalles de transferencia", "ur": "منتقلی کی تفصیل",
        "ar": "تفاصيل النقل", "hi": "स्थानांतरण विवरण", "bn": "স্থানান্তরের বিবরণ",
    },
    "Saving to": {
        "es": "Guardando en", "ur": "محفوظ ہو رہا ہے", "ar": "الحفظ في",
        "hi": "यहाँ सहेजा जा रहा है", "bn": "সংরক্ষণের স্থান",
    },
    "Image preview": {
        "es": "Vista previa de imagen", "ur": "تصویر کا پیش منظر",
        "ar": "معاينة الصورة", "hi": "छवि पूर्वावलोकन", "bn": "ছবির পূর্বরূপ",
    },
    "History": {
        "es": "Historial", "ur": "سرگزشت", "ar": "السجل", "hi": "इतिहास", "bn": "ইতিহাস",
    },
    "Pause / resume": {
        "es": "Pausar / reanudar", "ur": "روکیں / دوبارہ شروع کریں",
        "ar": "إيقاف مؤقت / استئناف", "hi": "रोकें / फिर शुरू करें",
        "bn": "বিরতি / পুনরায় শুরু",
    },
    "Resume / retry": {
        "es": "Reanudar / reintentar", "ur": "جاری رکھیں / دوبارہ کوشش",
        "ar": "استئناف / إعادة المحاولة", "hi": "जारी / पुनः प्रयास",
        "bn": "চালিয়ে যান / আবার চেষ্টা",
    },
    "Cancel selected": {
        "es": "Cancelar seleccionado", "ur": "منتخب منسوخ کریں",
        "ar": "إلغاء المحدد", "hi": "चुना हुआ रद्द करें", "bn": "নির্বাচিত বাতিল",
    },
    "Open downloads folder": {
        "es": "Abrir carpeta de descargas", "ur": "ڈاؤن لوڈ فولڈر کھولیں",
        "ar": "فتح مجلد التنزيلات", "hi": "डाउनलोड फ़ोल्डर खोलें",
        "bn": "ডাউনলোড ফোল্ডার খুলুন",
    },
    "Download speed": {
        "es": "Velocidad de descarga", "ur": "ڈاؤن لوڈ کی رفتار",
        "ar": "سرعة التنزيل", "hi": "डाउनलोड गति", "bn": "ডাউনলোডের গতি",
    },
    "Limit for this download": {
        "es": "Límite de esta descarga", "ur": "اس ڈاؤن لوڈ کی حد",
        "ar": "حد هذا التنزيل", "hi": "इस डाउनलोड की सीमा", "bn": "এই ডাউনলোডের সীমা",
    },
    "Shared limit for all downloads": {
        "es": "Límite compartido de todas las descargas",
        "ur": "تمام ڈاؤن لوڈز کی مشترکہ حد",
        "ar": "الحد المشترك لكل التنزيلات",
        "hi": "सभी डाउनलोड की साझा सीमा",
        "bn": "সব ডাউনলোডের সম্মিলিত সীমা",
    },
    "Verify downloaded file": {
        "es": "Verificar archivo descargado", "ur": "ڈاؤن لوڈ فائل کی تصدیق",
        "ar": "التحقق من الملف الذي تم تنزيله",
        "hi": "डाउनलोड की गई फ़ाइल सत्यापित करें",
        "bn": "ডাউনলোড করা ফাইল যাচাই",
    },
    "Proxy (optional)": {
        "es": "Proxy (opcional)", "ur": "پراکسی (اختیاری)",
        "ar": "وكيل (اختياري)", "hi": "प्रॉक्सी (वैकल्पिक)",
        "bn": "প্রক্সি (ঐচ্ছিক)",
    },
    "Browser cookies": {
        "es": "Cookies del navegador", "ur": "براؤزر کوکیز",
        "ar": "ملفات تعريف ارتباط المتصفح",
        "hi": "ब्राउज़र कुकीज़", "bn": "ব্রাউজার কুকি",
    },
    "Custom HTTP headers": {
        "es": "Encabezados HTTP personalizados",
        "ur": "حسب ضرورت HTTP ہیڈرز",
        "ar": "ترويسات HTTP مخصصة",
        "hi": "कस्टम HTTP हेडर", "bn": "কাস্টম HTTP হেডার",
    },
    "Retry attempts": {
        "es": "Intentos de reintento", "ur": "دوبارہ کوششیں",
        "ar": "محاولات إعادة التنزيل", "hi": "पुनः प्रयास", "bn": "পুনরায় চেষ্টার সংখ্যা",
    },
    "Start at (local time)": {
        "es": "Iniciar a (hora local)", "ur": "شروع کریں (مقامی وقت)",
        "ar": "البدء في (التوقيت المحلي)", "hi": "शुरू करें (स्थानीय समय)",
        "bn": "শুরু (স্থানীয় সময়)",
    },
    "Save to cloud": {
        "es": "Guardar en la nube", "ur": "کلاؤڈ میں محفوظ کریں",
        "ar": "الحفظ إلى السحابة", "hi": "क्लाउड में सहेजें",
        "bn": "ক্লাউডে সংরক্ষণ",
    },
    "Open selected location": {
        "es": "Abrir ubicación seleccionada",
        "ur": "منتخب کردہ مقام کھولیں",
        "ar": "فتح الموقع المحدد",
        "hi": "चुना गया स्थान खोलें",
        "bn": "নির্বাচিত অবস্থান খুলুন",
    },
}

URDU_CORE_TRANSLATIONS = {
    "All tasks": "تمام کام",
    "Downloading": "ڈاؤن لوڈ ہو رہا ہے",
    "Completed": "مکمل",
    "Media library": "میڈیا لائبریری",
    "Tools & utilities": "اوزار اور سہولیات",
    "Convert to MP3": "MP3 میں تبدیل کریں",
    "Image tools": "تصویری اوزار",
    "Image gallery": "تصاویر کی گیلری",
    "Download and organize\nlocal media": "مقامی میڈیا ڈاؤن لوڈ اور منظم کریں",
    "Paste a link, choose where to save it, and add it to your queue.": (
        "لنک چسپاں کریں، محفوظ کرنے کی جگہ منتخب کریں، پھر فہرست میں شامل کریں۔"
    ),
    "Use recommended": "تجویز کردہ ترتیبات استعمال کریں",
    "Auto-fill copied links": "کاپی کیے گئے لنک خودکار طور پر شامل کریں",
    "Dark mode": "ڈارک موڈ",
    "Link": "لنک",
    "Source": "ماخذ",
    "Media": "میڈیا",
    "Resolution": "ویڈیو معیار",
    "Playlist": "پلے لسٹ",
    "Add download": "ڈاؤن لوڈ شامل کریں",
    "Batch": "ایک ساتھ کئی",
    "Sequence": "ترتیب",
    "Browse": "منتخب کریں",
    "Statistics dashboard": "اعداد و شمار کا ڈیش بورڈ",
    "Total downloads": "کل ڈاؤن لوڈز",
    "Completed files": "مکمل فائلیں",
    "Success rate": "کامیابی کی شرح",
    "Failed or stopped": "ناکام یا رکے ہوئے",
    "Top source domains": "نمایاں ماخذ ڈومین",
    "No source domains recorded yet.": "ابھی تک کوئی ماخذ ڈومین محفوظ نہیں ہوا۔",
    "No task selected": "کوئی کام منتخب نہیں",
    "Select a task before copying its link.": "لنک کاپی کرنے سے پہلے ایک کام منتخب کریں۔",
    "More settings": "مزید ترتیبات",
    "Overall progress": "مجموعی پیش رفت",
    "Right-click an image download for image tools.": (
        "تصویری اوزار کے لیے ڈاؤن لوڈ کی گئی تصویر پر دایاں کلک کریں۔"
    ),
    "Status": "حالت",
    "Progress": "پیش رفت",
    "Transfer details": "منتقلی کی تفصیل",
    "Saving to": "یہاں محفوظ ہو رہا ہے",
    "Media preview": "میڈیا کا پیش نظارہ",
    "No item selected": "کوئی آئٹم منتخب نہیں",
    "Select a file to preview": "پیش نظارہ کے لیے فائل منتخب کریں",
    "Choose an existing file or select a downloaded task.": (
        "موجودہ فائل منتخب کریں یا ڈاؤن لوڈ کیا گیا کام چنیں۔"
    ),
    "Show file": "فائل دکھائیں",
    "Pause / resume": "روکیں / جاری رکھیں",
    "Resume / retry": "جاری رکھیں / دوبارہ کوشش کریں",
    "Cancel selected": "منتخب کام منسوخ کریں",
    "History": "تاریخچہ",
    "Hide selected": "منتخب کام چھپائیں",
    "Restore selected": "منتخب کام بحال کریں",
    "Clear finished": "مکمل کام صاف کریں",
    "Show hidden": "چھپے ہوئے دکھائیں",
    "Help": "مدد",
    "General": "عام",
    "Language": "زبان",
    "Accessibility": "رسائی کی سہولیات",
    "Use larger text": "بڑا متن استعمال کریں",
    "High contrast": "زیادہ تضاد",
    "Check for updates at startup": "شروع ہوتے وقت اپ ڈیٹس دیکھیں",
    "Check for updates now": "ابھی اپ ڈیٹس دیکھیں",
    "Record local diagnostic events": "مقامی تشخیصی واقعات محفوظ کریں",
    "Export local diagnostics…": "مقامی تشخیصی معلومات برآمد کریں…",
    "Speed & checks": "رفتار اور تصدیق",
    "Connection": "کنکشن",
    "Download speed": "ڈاؤن لوڈ کی رفتار",
    "Limit for this download": "اس ڈاؤن لوڈ کی حد",
    "Shared limit for all downloads": "تمام ڈاؤن لوڈز کی مشترکہ حد",
    "Verify downloaded file": "ڈاؤن لوڈ فائل کی تصدیق کریں",
    "Proxy (optional)": "پراکسی (اختیاری)",
    "Browser cookies": "براؤزر کوکیز",
    "Custom HTTP headers": "حسب ضرورت HTTP ہیڈرز",
    "Retry attempts": "دوبارہ کوششوں کی تعداد",
    "Schedule & files": "شیڈول اور فائلیں",
    "Start at (local time)": "شروع ہونے کا وقت (مقامی)",
    "Save to cloud": "کلاؤڈ میں محفوظ کریں",
    "Keyboard shortcuts:": "کی بورڈ شارٹ کٹس:",
    "Ctrl+L — focus link field": "Ctrl+L — لنک والے خانے پر جائیں",
    "Ctrl+J — focus download list": "Ctrl+J — ڈاؤن لوڈ فہرست پر جائیں",
    "Alt+S — focus progress status": "Alt+S — پیش رفت کی حالت پر جائیں",
    "Space — pause/resume when the download list is focused": (
        "Space — ڈاؤن لوڈ فہرست منتخب ہونے پر روکیں یا جاری رکھیں"
    ),
    "Press F1 for help. Use Tab and Shift+Tab to move between controls.": (
        "مدد کے لیے F1 دبائیں۔ کنٹرولز کے درمیان جانے کے لیے Tab اور Shift+Tab استعمال کریں۔"
    ),
    "Language saved": "زبان محفوظ ہو گئی",
    "Smart Downloader help": "Smart Downloader کی مدد",
    "Keyboard: Ctrl+, Settings · F1 Help · Ctrl+Enter Add download · Ctrl+O Open selected location": (
        "کی بورڈ: Ctrl+, ترتیبات · F1 مدد · Ctrl+Enter ڈاؤن لوڈ شامل کریں · "
        "Ctrl+O منتخب مقام کھولیں"
    ),
    "Restart Smart Downloader to apply the selected language.": (
        "منتخب زبان لاگو کرنے کے لیے Smart Downloader دوبارہ شروع کریں۔"
    ),
}

for _source_text, _urdu_text in URDU_CORE_TRANSLATIONS.items():
    TRANSLATIONS.setdefault(_source_text, {})["ur"] = _urdu_text


def translate(text: str, language: str = "en") -> str:
    language_code = LANGUAGES.get(language, language)
    return TRANSLATIONS.get(text, {}).get(language_code, text)
