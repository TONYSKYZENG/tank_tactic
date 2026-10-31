import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from PyQt5.QtCore import QObject, pyqtSignal

class I18nManager(QObject):
    """
    国际化多语言管理器 (支持 YAML 字典层级解析与实时响应切换)
    """
    language_changed = pyqtSignal(str)

    _instance: Optional['I18nManager'] = None

    @classmethod
    def instance(cls) -> 'I18nManager':
        if cls._instance is None:
            cls._instance = I18nManager()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_dir = Path(__file__).resolve().parent
        self.current_locale = "zh"
        self.translations: Dict[str, Dict[str, Any]] = {}
        self._load_translations()

    def _load_translations(self):
        for yml_file in self.base_dir.glob("*.yml"):
            locale = yml_file.stem.lower()
            try:
                with open(yml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    self.translations[locale] = data
            except Exception as e:
                print(f"[i18n] 载入语言文件失败 {yml_file}: {e}")

    def get_available_languages(self) -> List[str]:
        return list(self.translations.keys())

    def set_language(self, locale: str):
        locale = locale.lower()
        if locale not in self.translations:
            # 兼容带有语言地区后缀
            matched = [k for k in self.translations if k.startswith(locale[:2])]
            if matched:
                locale = matched[0]
            else:
                return

        if self.current_locale != locale:
            self.current_locale = locale
            self.language_changed.emit(self.current_locale)

    def get_language(self) -> str:
        return self.current_locale

    def t(self, key_path: str, default: Optional[str] = None, **kwargs) -> str:
        """
        通过点分路径获取本地化翻译文本，如 t('editor.modes.map')
        """
        curr_dict = self.translations.get(self.current_locale, {})
        keys = key_path.split(".")
        val: Any = curr_dict

        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                val = None
                break

        if val is None:
            # 回退到英文
            en_dict = self.translations.get("en", {})
            val = en_dict
            for k in keys:
                if isinstance(val, dict) and k in val:
                    val = val[k]
                else:
                    val = None
                    break

        if val is None:
            val = default if default is not None else key_path

        if isinstance(val, str) and kwargs:
            try:
                return val.format(**kwargs)
            except Exception:
                return val
        return str(val) if val is not None else key_path


# 全局便捷代理函数与单例
i18n = I18nManager.instance()

def tr(key_path: str, default: Optional[str] = None, **kwargs) -> str:
    return i18n.t(key_path, default=default, **kwargs)

def t(key_path: str, default: Optional[str] = None, **kwargs) -> str:
    return i18n.t(key_path, default=default, **kwargs)
