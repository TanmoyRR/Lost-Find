import django.template.context

original_base_copy = django.template.context.BaseContext.__copy__

def patched_base_copy(self):
    duplicate = object.__new__(type(self))
    duplicate.dicts = self.dicts[:]
    return duplicate

django.template.context.BaseContext.__copy__ = patched_base_copy