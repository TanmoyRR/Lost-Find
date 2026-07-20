# Python 3.14 compatibility fix for Django's Context.__copy__
import sys
import copy as _copy_module

if sys.version_info >= (3, 14):
    import django.template.context as ctx_module
    original_copy = ctx_module.RenderContext.__copy__ if hasattr(ctx_module.RenderContext, '__copy__') else None
    def patched_copy(self):
        cls = self.__class__
        result = cls.__new__(cls)
        result.dicts = self.dicts[:]
        result._template_blocks = getattr(self, '_template_blocks', {})
        return result
    ctx_module.RenderContext.__copy__ = patched_copy
