"""Arabic controls for the same validated backend resource policy."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFormLayout,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit,QCheckBox,QPlainTextEdit,QLabel
from src.core.resource_policy import ProtectionConfig,read_config
from src.desktop.paths import data_directory


LABELS={
'sampling_interval_seconds':'فاصل القياس بالثواني','gpu_enter_percent':'دخول: ضغط GPU الخارجي %','cpu_enter_percent':'دخول: ضغط CPU الخارجي %','cpu_hot_core_percent':'دخول: نواة ساخنة %','pressure_hold_seconds':'نافذة استمرار الضغط بالثواني','gpu_exit_percent':'خروج: GPU أقل من %','cpu_exit_percent':'خروج: CPU والنواة أقل من %','exit_hold_seconds':'مهلة زوال جميع الأسباب بالثواني','minimum_mode_dwell_seconds':'أقل مدة للحماية بالثواني','physical_cpu_core_limit':'عدد الأنوية الفعلية (غير حصرية)','generation_threads':'خيوط توليد النص','prompt_threads':'خيوط معالجة المدخل','protected_cpu_nice':'أولوية nice عندما يمكن استعادتها','protected_context':'سياق النموذج المحمي','memory_reserve_gb':'احتياطي الذاكرة GB، بالإضافة للتقدير'}


class ResourceSettings(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setLayoutDirection(Qt.LayoutDirection.RightToLeft);self.setObjectName('resource-settings');form=QFormLayout(self);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.initial=read_config(data_directory(),{'mode':'auto'});cfg=self.initial;self.controls={}
        note=QLabel('الحماية تنقل الاستدلال المتوافق إلى GPU ثانوي وتحد أنوية العمال. الأدوار غير المسندة تنتظر، ولا عودة صامتة للبطاقة الرئيسية. القياسات غير المتاحة تبقى مجهولة.');note.setWordWrap(True);form.addRow(note)
        mode=QComboBox()
        for text,value in [('تلقائي — Auto','auto'),('عادي يدوي — Normal','normal'),('محمي يدوي — Protected','protected')]:mode.addItem(text,value)
        mode.setCurrentIndex(mode.findData(cfg.mode));self.controls['mode']=mode;form.addRow('وضع الموارد',mode)
        gpu=QComboBox();gpu.addItem('لم يُحدد GPU ثانوي','')
        try:
            from src.backends.devices import probe_devices
            for d in probe_devices():
                if d.get('stable_id'):gpu.addItem(d['description']+' · '+d['pci_id'],d['stable_id'])
        except Exception:pass
        i=gpu.findData(cfg.protected_gpu)
        if i<0:gpu.addItem('جهاز محفوظ غير متاح: '+cfg.protected_gpu,cfg.protected_gpu);i=gpu.count()-1
        gpu.setCurrentIndex(i);self.controls['protected_gpu']=gpu;form.addRow('هوية البطاقة الثانوية',gpu)
        folder=QLineEdit(cfg.protected_models_dir);self.controls['protected_models_dir']=folder;form.addRow('مجلد أوزان الملف المحمي',folder)
        for key,label in [('game_detection','كشف هوية اللعبة دون اشتراط ضغط مرتفع'),('cpu_offload_fallback','السماح صراحةً ببديل CPU مع فحص RAM')]:
            w=QCheckBox(label);w.setChecked(getattr(cfg,key));self.controls[key]=w;form.addRow(w)
        for key,label in LABELS.items():
            field=ProtectionConfig.model_fields[key];value=getattr(cfg,key);w=QDoubleSpinBox() if field.annotation is float else QSpinBox()
            limits={type(m).__name__:m for m in field.metadata};lo=getattr(limits.get('Ge'),'ge',0);hi=getattr(limits.get('Le'),'le',32768)
            w.setRange(lo,hi)
            if isinstance(w,QDoubleSpinBox):w.setDecimals(2)
            w.setValue(value);self.controls[key]=w;form.addRow(label,w)
        self.controls['physical_cpu_core_limit'].valueChanged.connect(self.core_limit)
        for key,label in [('process_rules','أسماء تنفيذية أو مسارات ألعاب دقيقة — سطر لكل قاعدة'),('exclusions','استثناءات دقيقة — سطر لكل اسم أو مسار')]:
            w=QPlainTextEdit('\n'.join(r.value for r in getattr(cfg,key)));w.setMaximumHeight(80);self.controls[key]=w;form.addRow(label,w)
        import yaml
        from src.runtime import ROOT
        models=yaml.safe_load((ROOT/'configs/models.yaml').read_text())['models'];self.maps={}
        for tier,label in [('expert','مخطط Expert'),('coder','مبرمج Coder'),('daily','محادثة Daily'),('fast','سريع Fast'),('vision','رؤية Vision'),('embedding','Embedding — يتطلب محركًا متاحًا')]:
            w=QComboBox();w.addItem('غير مسند — انتظار','')
            for mid,info in models.items():w.addItem(info.get('name',mid),mid)
            w.setCurrentIndex(max(0,w.findData(cfg.tier_models.get(tier,''))));self.maps[tier]=w;form.addRow(label,w)
        warning=QLabel('اختيار وزن لا يثبت جاهزيته. تُفحص الملفات والذاكرة الفعلية لكل دور، بما فيه المخطط. Whisper GPU محجوب أثناء الحماية؛ الرؤية تتطلب نموذجًا ومعالج صور متوافقين. لا يتم تنزيل أوزان أو إغلاق تطبيقاتك.');warning.setWordWrap(True);form.addRow(warning)
        for key,w in self.controls.items():w.setObjectName('resource-'+key)

    def core_limit(self,count):
        for key in ('generation_threads','prompt_threads'):self.controls[key].setMaximum(count)

    def value(self):
        values=self.initial.model_dump()
        for key,w in self.controls.items():
            if isinstance(w,QComboBox):value=w.currentData()
            elif isinstance(w,QCheckBox):value=w.isChecked()
            elif isinstance(w,QPlainTextEdit):
                value=[{'kind':'path' if line.startswith('/') else 'name','value':line.strip()} for line in w.toPlainText().splitlines() if line.strip()]
            elif isinstance(w,QLineEdit):value=w.text().strip()
            else:value=w.value()
            values[key]=value
        values['tier_models']={k:w.currentData() for k,w in self.maps.items() if w.currentData()}
        cfg=ProtectionConfig.model_validate(values)
        if cfg.protected_models_dir and not Path(cfg.protected_models_dir).is_dir():raise ValueError('مجلد أوزان الملف المحمي غير موجود')
        return cfg
